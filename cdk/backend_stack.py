"""Backend infrastructure stack for the resume tailoring platform."""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigateway,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_cognito as cognito,
)
from aws_cdk.aws_cognito_identitypool_alpha import IdentityPool
from constructs import Construct


class BackendStack(Stack):
    """Creates serverless backend resources including S3, DynamoDB, Lambda, and API Gateway."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        user_pool: cognito.UserPool,
        identity_pool: IdentityPool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

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

        # Shared environment for Lambdas
        lambda_env = {
            "BUCKET_NAME": bucket.bucket_name,
            "TABLE_NAME": table.table_name,
            "BEDROCK_MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0",
            "OUTPUT_PREFIX": "generated",
        }

        # Upload Lambda
        upload_function = lambda_.Function(
            self,
            "ResumeUploadFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/upload_handler"),
            memory_size=1024,
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_MONTH,
            environment=lambda_env,
        )

        # Generate Lambda (heavier workload)
        generate_function = lambda_.Function(
            self,
            "ResumeGenerateFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/generate_handler"),
            memory_size=2048,  # override
            timeout=Duration.minutes(15),  # override
            log_retention=logs.RetentionDays.ONE_MONTH,
            environment=lambda_env,
        )

        # Download Lambda
        download_function = lambda_.Function(
            self,
            "ResumeDownloadFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/download_handler"),
            memory_size=1024,
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_MONTH,
            environment=lambda_env,
        )

        # Grants
        bucket.grant_read_write(upload_function)
        bucket.grant_read_write(generate_function)
        bucket.grant_read(download_function)

        table.grant_read_write_data(upload_function)
        table.grant_read_write_data(generate_function)
        table.grant_read_data(download_function)

        # IAM policies
        generate_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=["*"],
            )
        )

        generate_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["comprehend:ContainsPiiEntities"],
                resources=["*"],
            )
        )

        download_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[bucket.arn_for_objects("*")],
            )
        )

        # API Gateway
        api = apigateway.RestApi(
            self,
            "ResumeApi",
            rest_api_name="ResumeTailorService",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["*"],
            ),
        )

        api.root.add_resource("upload").add_method("POST", apigateway.LambdaIntegration(upload_function))
        api.root.add_resource("generate").add_method("POST", apigateway.LambdaIntegration(generate_function))
        api.root.add_resource("download").add_method("GET", apigateway.LambdaIntegration(download_function))

        self.api_url = api.url
        self.bucket = bucket
        self.table = table
