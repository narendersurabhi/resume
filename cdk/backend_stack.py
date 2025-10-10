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
from aws_cdk import CfnOutput
from aws_cdk.aws_lambda_python_alpha import PythonFunction, PythonLayerVersion  # add import
from aws_cdk import aws_lambda as lambda_

class BackendStack(Stack):
    """Creates serverless backend resources including S3, DynamoDB, Lambda, and API Gateway."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
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

        # generate_function = PythonFunction(
        #     self,
        #     "ResumeGenerateFunction",
        #     entry="lambdas/generate_handler",      # folder with app.py and requirements.txt
        #     index="app.py",                        # your file name
        #     handler="handler",
        #     runtime=lambda_.Runtime.PYTHON_3_12,
        #     memory_size=2048,
        #     timeout=Duration.minutes(15),
        #     environment=lambda_env,
        #     # optional: exclude boto3 since it’s in the runtime
        #     bundling={"asset_excludes": ["boto3", "botocore"],}
        # )

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

        docx_layer = lambda_.LayerVersion(
            self, "DocxLayer",
            code=lambda_.Code.from_asset("layers/docx_layer"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            compatible_architectures=[lambda_.Architecture.X86_64],  # use ARM_64 if your fn is arm
            description="python-docx + lxml for generate handler",
        )
        generate_function.add_layers(docx_layer)

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
            self, "ResumeApi",
            rest_api_name="ResumeTailorService",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["*"],
                allow_credentials=False,  # set True only if you use cookies
            ),
        )


        api.root.add_resource("upload").add_method("POST", apigateway.LambdaIntegration(upload_function))
        api.root.add_resource("generate").add_method("POST", apigateway.LambdaIntegration(generate_function))
        api.root.add_resource("download").add_method("GET", apigateway.LambdaIntegration(download_function))

        self.api_url = api.url
        self.bucket = bucket
        self.table = table

        # CfnOutput(self, "ApiUrl", value=self.api_url)
        # CfnOutput(self, "StorageBucketName", value=bucket.bucket_name)
        # CfnOutput(self, "MetadataTableName", value=table.table_name) 

        CfnOutput(self, "ApiUrl", value=self.api_url, export_name="ResumeApiUrl")