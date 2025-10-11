"""Backend infrastructure stack for the resume tailoring platform."""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_apigateway as apigateway,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct
import os


class BackendStack(Stack):
    """Creates serverless backend resources including S3, DynamoDB, Lambda, and API Gateway."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cf_dist_id = os.getenv("CF_DIST_ID", "")
        CDK_DEFAULT_REGION = os.getenv("CDK_DEFAULT_REGION")

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

        allowed_origin = self.node.try_get_context("frontendOrigin") or "*"
        
        lambda_env = {
            "BUCKET_NAME": bucket.bucket_name,
            "TABLE_NAME": table.table_name,
            "BEDROCK_MODEL_ID": 'openai.gpt-oss-120b-1:0',
            "OUTPUT_PREFIX": "generated",    
            "CF_DIST_ID": cf_dist_id,
            "FRONTEND_ORIGIN": f"https://{cf_dist_id}.cloudfront.net",
            "CDK_DEFAULT_REGION": CDK_DEFAULT_REGION,
        }

        # layer
        docx_layer = lambda_.LayerVersion(
            self, "DocxLayer",
            code=lambda_.Code.from_asset("layers/docx_layer/layer.zip"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="python-docx + lxml"
        )

        # Lambdas

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

        generate_function = lambda_.Function(
            self,
            "ResumeGenerateFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/generate_handler"),
            memory_size=2048,
            timeout=Duration.minutes(15),
            log_retention=logs.RetentionDays.ONE_MONTH,
            environment=lambda_env,
            layers=[docx_layer], 
        )

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

        generate_function.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[f"arn:aws:bedrock:{self.region}::foundation-model/openai.gpt-oss-120b-1:0"]))

        frontend_domain = f"https://{cf_dist_id}.cloudfront.net"  # put your CF URL here

        # API Gateway with permissive CORS (adjust as needed)
        api = apigateway.RestApi(
            self,
            "ResumeApi",
            rest_api_name="ResumeTailorService",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=[frontend_domain],
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

        api.add_gateway_response(
            "Default4xx",
            type=rtype_4xx,
            response_headers={
                "Access-Control-Allow-Origin": f"'{frontend_domain}'",
                "Access-Control-Allow-Headers": "'*'",
                "Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
            },
        )
        api.add_gateway_response(
            "Default5xx",
            type=rtype_5xx,
            response_headers={
                "Access-Control-Allow-Origin": f"'{frontend_domain}'",
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
