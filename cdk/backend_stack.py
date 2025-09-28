"""Backend infrastructure stack for the resume tailoring platform."""
from aws_cdk import (Duration, RemovalPolicy, Stack, aws_apigateway as apigateway,
                     aws_dynamodb as dynamodb, aws_iam as iam, aws_lambda as lambda_,
                     aws_logs as logs, aws_s3 as s3)
from constructs import Construct

from aws_cognito_identitypool_alpha import IdentityPool
from aws_cdk import aws_cognito as cognito


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

        bucket = s3.Bucket(
            self,
            "ResumeStorageBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        stack = Stack.of(self)
        textract_principal = iam.ServicePrincipal("textract.amazonaws.com")
        textract_access_prefixes = [
            bucket.arn_for_objects("*/approved/*"),
            bucket.arn_for_objects("*/jobs/*"),
            bucket.arn_for_objects("*/template/*"),
        ]

        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowTextractReadTenantObjects",
                effect=iam.Effect.ALLOW,
                principals=[textract_principal],
                actions=["s3:GetObject"],
                resources=textract_access_prefixes,
                conditions={
                    "StringEquals": {"aws:SourceAccount": stack.account},
                },
            )
        )

        if bucket.encryption_key:
            bucket.encryption_key.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="AllowTextractUseOfKey",
                    effect=iam.Effect.ALLOW,
                    principals=[textract_principal],
                    actions=["kms:Decrypt", "kms:GenerateDataKey"],
                    resources=["*"],
                    conditions={
                        "StringEquals": {"aws:SourceAccount": stack.account},
                        "ArnLike": {
                            "aws:SourceArn": stack.format_arn(
                                service="textract", resource="*"
                            )
                        },
                    },
                )
            )

        table = dynamodb.Table(
            self,
            "ResumeMetadataTable",
            partition_key=dynamodb.Attribute(name="tenantId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="resourceId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        lambda_env = {
            "BUCKET_NAME": bucket.bucket_name,
            "TABLE_NAME": table.table_name,
            "BEDROCK_MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0",
            "OUTPUT_PREFIX": "generated",
        }

        common_lambda_kwargs = {
            "runtime": lambda_.Runtime.PYTHON_3_12,
            "memory_size": 1024,
            "timeout": Duration.minutes(5),
            "log_retention": logs.RetentionDays.ONE_MONTH,
            "environment": lambda_env,
        }

        upload_function = lambda_.Function(
            self,
            "ResumeUploadFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/upload_handler"),
            **common_lambda_kwargs,
        )

        generate_function = lambda_.Function(
            self,
            "ResumeGenerateFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/generate_handler"),
            timeout=Duration.minutes(15),
            memory_size=2048,
            **common_lambda_kwargs,
        )

        download_function = lambda_.Function(
            self,
            "ResumeDownloadFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/download_handler"),
            **common_lambda_kwargs,
        )

        bucket.grant_read_write(upload_function)
        bucket.grant_read_write(generate_function)
        bucket.grant_read(download_function)

        table.grant_read_write_data(upload_function)
        table.grant_read_write_data(generate_function)
        table.grant_read_data(download_function)

        bedrock_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
            ],
            resources=["*"],
        )
        generate_function.add_to_role_policy(bedrock_policy)

        comprehend_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "comprehend:ContainsPiiEntities",
            ],
            resources=["*"],
        )
        generate_function.add_to_role_policy(comprehend_policy)

        s3_presign_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject"],
            resources=[bucket.arn_for_objects("*")],
        )
        download_function.add_to_role_policy(s3_presign_policy)

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

        upload_integration = apigateway.LambdaIntegration(upload_function)
        generate_integration = apigateway.LambdaIntegration(generate_function)
        download_integration = apigateway.LambdaIntegration(download_function)

        uploads = api.root.add_resource("upload")
        uploads.add_method("POST", upload_integration)

        generate = api.root.add_resource("generate")
        generate.add_method("POST", generate_integration)

        downloads = api.root.add_resource("download")
        downloads.add_method("GET", download_integration)

        self.api_url = api.url
        self.bucket = bucket
        self.table = table
