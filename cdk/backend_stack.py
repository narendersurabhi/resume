"""Backend infrastructure stack for the resume tailoring platform."""
from aws_cdk import (
    CfnParameter,
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    Fn,
    aws_apigateway as apigateway,
    aws_dynamodb as dynamodb,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_cognito as cognito,
)
from constructs import Construct
import os


class BackendStack(Stack):
    """Creates serverless backend resources including S3, DynamoDB, Lambda, and API Gateway."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cf_dist_id = os.getenv("CF_DIST_ID", "")
        CDK_DEFAULT_REGION = os.getenv("CDK_DEFAULT_REGION")
        frontend_origin_env = os.getenv("FRONTEND_ORIGIN", "").strip()

        # Parameters controlling container image tags supplied by the pipeline
        download_image_tag = CfnParameter(
            self,
            "DownloadImageTag",
            type="String",
            default="latest",
            description="Tag for the download Lambda container image.",
        )
        generate_image_tag = CfnParameter(
            self,
            "GenerateImageTag",
            type="String",
            default="latest",
            description="Tag for the generate Lambda container image.",
        )
        upload_image_tag = CfnParameter(
            self,
            "UploadImageTag",
            type="String",
            default="latest",
            description="Tag for the upload Lambda container image.",
        )

        # Storage
        bucket = s3.Bucket(
            self,
            "ResumeStorageBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        table = dynamodb.Table(
            self,
            "ResumeMetadataTable",
            partition_key=dynamodb.Attribute(name="tenantId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="resourceId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Determine the frontend origin for CORS
        # Priority: FRONTEND_ORIGIN env var -> explicit context value -> fallback '*'
        allowed_origin_ctx = self.node.try_get_context("frontendOrigin")
        if frontend_origin_env:
            frontend_domain = frontend_origin_env
        elif allowed_origin_ctx and str(allowed_origin_ctx).strip():
            frontend_domain = str(allowed_origin_ctx).strip()
        else:
            frontend_domain = "*"

        lambda_env = {
            "BUCKET_NAME": bucket.bucket_name,
            "TABLE_NAME": table.table_name,
            "BEDROCK_MODEL_ID": 'openai.gpt-oss-120b-1:0',
            "OUTPUT_PREFIX": "generated",    
            "CF_DIST_ID": cf_dist_id,
            "FRONTEND_ORIGIN": frontend_domain if frontend_domain != "*" else "*",
            "CDK_DEFAULT_REGION": CDK_DEFAULT_REGION,
        }

        # ECR repositories hosting the Lambda container images
        download_repo = ecr.Repository.from_repository_name(
            self, "DownloadRepository", "resume-download"
        )
        generate_repo = ecr.Repository.from_repository_name(
            self, "GenerateRepository", "resume-generate"
        )
        upload_repo = ecr.Repository.from_repository_name(
            self, "UploadRepository", "resume-upload"
        )

        common_image_props = dict(
            architecture=lambda_.Architecture.X86_64,
            environment=lambda_env,
            memory_size=1024,
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        upload_function = lambda_.DockerImageFunction(
            self,
            "ResumeUploadFunction",
            code=lambda_.DockerImageCode.from_ecr(
                repository=upload_repo,
                tag_or_digest=upload_image_tag.value_as_string,
            ),
            **common_image_props,
        )

        generate_function = lambda_.DockerImageFunction(
            self,
            "ResumeGenerateFunction",
            code=lambda_.DockerImageCode.from_ecr(
                repository=generate_repo,
                tag_or_digest=generate_image_tag.value_as_string,
            ),
            architecture=lambda_.Architecture.X86_64,
            environment=lambda_env,
            memory_size=2048,
            timeout=Duration.minutes(15),
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        download_function = lambda_.DockerImageFunction(
            self,
            "ResumeDownloadFunction",
            code=lambda_.DockerImageCode.from_ecr(
                repository=download_repo,
                tag_or_digest=download_image_tag.value_as_string,
            ),
            **common_image_props,
        )

        # Grants
        bucket.grant_read_write(upload_function)
        bucket.grant_read_write(generate_function)
        bucket.grant_read(download_function)

        table.grant_read_write_data(upload_function)
        table.grant_read_write_data(generate_function)
        table.grant_read_data(download_function)

        generate_function.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[f"arn:aws:bedrock:{self.region}::foundation-model/openai.gpt-oss-120b-1:0"]))

        # API Gateway with CORS (adjust as needed)
        api = apigateway.RestApi(
            self,
            "ResumeApi",
            rest_api_name="ResumeTailorService",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=(apigateway.Cors.ALL_ORIGINS if frontend_domain == "*" else [frontend_domain]),
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["*"],
                allow_credentials=False,  # set True only if sending cookies
            ),
        )

        # Ensure preflight still matches your origins
        # after: api = apigateway.RestApi(...)
        # handle enum name differences across CDK versions
        # Enum names vary by CDK version
        rtype_4xx = getattr(apigateway.ResponseType, "DEFAULT_4_XX", None) or getattr(apigateway.ResponseType, "DEFAULT_4XX")
        rtype_5xx = getattr(apigateway.ResponseType, "DEFAULT_5_XX", None) or getattr(apigateway.ResponseType, "DEFAULT_5XX")

        # Access-Control-Allow-Origin header formatting for gateway responses
        acao_value = "'*'" if frontend_domain == "*" else f"'{frontend_domain}'"

        api.add_gateway_response(
            "Default4xx",
            type=rtype_4xx,
            response_headers={
                "Access-Control-Allow-Origin": acao_value,
                "Access-Control-Allow-Headers": "'*'",
                "Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
            },
        )
        api.add_gateway_response(
            "Default5xx",
            type=rtype_5xx,
            response_headers={
                "Access-Control-Allow-Origin": acao_value,
                "Access-Control-Allow-Headers": "'*'",
                "Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
            },
        )

        api.root.add_resource("upload").add_method("POST", apigateway.LambdaIntegration(upload_function))
        api.root.add_resource("generate").add_method("POST", apigateway.LambdaIntegration(generate_function))
        api.root.add_resource("download").add_method("GET", apigateway.LambdaIntegration(download_function))

        self.api_url = api.url
        self.bucket = bucket
        self.table = table

        CfnOutput(self, "ApiUrl", value=self.api_url, export_name="ResumeApiUrl")

        # --------------------
        # Jobs store (DynamoDB + S3) for tailoring/rendering workflows
        # --------------------
        jobs_table = dynamodb.Table(
            self,
            "ResumeJobs",
            partition_key=dynamodb.Attribute(name="jobId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        jobs_bucket = s3.Bucket(
            self,
            "ResumeJobsBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # Tailor (generate) Lambda - zip-based to avoid impacting existing container builds
        tailor_fn = lambda_.Function(
            self,
            "TailorHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/tailor_handler"),
            environment={
                "JOBS_BUCKET": jobs_bucket.bucket_name,
                "JOBS_TABLE": jobs_table.table_name,
                "MODEL_PROVIDER": "openai",
                "MODEL_ID": "gpt-4o-mini",
            },
            memory_size=512,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        render_fn = lambda_.Function(
            self,
            "RenderHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/render_handler"),
            environment={
                "JOBS_BUCKET": jobs_bucket.bucket_name,
                "JOBS_TABLE": jobs_table.table_name,
            },
            memory_size=512,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        jobs_bucket.grant_read_write(tailor_fn)
        jobs_bucket.grant_read_write(render_fn)
        jobs_table.grant_read_write_data(tailor_fn)
        jobs_table.grant_read_write_data(render_fn)

        # API routes for tailoring and rendering
        # Cognito authorizer using exported User Pool from AuthStack
        user_pool = cognito.UserPool.from_user_pool_id(
            self,
            "ImportedUserPool",
            Fn.import_value("ResumeUserPoolId"),
        )
        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            "ResumeApiAuthorizer",
            cognito_user_pools=[user_pool],
        )

        api.root.add_resource("tailor").add_method(
            "POST",
            apigateway.LambdaIntegration(tailor_fn),
            authorizer=authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )
        api.root.add_resource("render").add_method(
            "POST",
            apigateway.LambdaIntegration(render_fn),
            authorizer=authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )

        # Jobs list and status
        jobs_root = api.root.add_resource("jobs")
        jobs_root.add_method(
            "GET",
            apigateway.LambdaIntegration(tailor_fn),
            authorizer=authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )
        jobs_res = jobs_root.add_resource("{jobId}")
        jobs_res.add_method(
            "GET",
            apigateway.LambdaIntegration(tailor_fn),
            authorizer=authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO,
        )

