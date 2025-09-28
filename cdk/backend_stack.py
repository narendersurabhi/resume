"""Backend infrastructure stack defining API Gateway, Lambdas, Step Functions, and data stores."""
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
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct

from aws_cognito_identitypool_alpha import IdentityPool
from aws_cdk import aws_cognito as cognito


class BackendStack(Stack):
    """Creates the serverless backend supporting the resume tailoring workflow."""

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
            "ResumeArtifactsBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        table = dynamodb.Table(
            self,
            "ResumeJobsTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
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
            "UploadDispatcherFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/upload_handler"),
            **common_lambda_kwargs,
        )

        workflow_function = lambda_.Function(
            self,
            "TailorWorkflowStarter",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/workflow_handler"),
            **common_lambda_kwargs,
        )

        generate_function = lambda_.Function(
            self,
            "BedrockGenerateFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/generate_handler"),
            timeout=Duration.minutes(15),
            memory_size=2048,
            **common_lambda_kwargs,
        )

        validate_function = lambda_.Function(
            self,
            "ResumeValidateFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/validate_handler"),
            timeout=Duration.minutes(5),
            **common_lambda_kwargs,
        )

        render_function = lambda_.Function(
            self,
            "ResumeRenderFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/render_handler"),
            timeout=Duration.minutes(15),
            memory_size=3072,
            **common_lambda_kwargs,
        )

        status_function = lambda_.Function(
            self,
            "JobStatusFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/status_handler"),
            **common_lambda_kwargs,
        )

        download_function = lambda_.Function(
            self,
            "PresignDownloadFunction",
            handler="app.handler",
            code=lambda_.Code.from_asset("lambdas/download_handler"),
            **common_lambda_kwargs,
        )

        bucket.grant_read_write(upload_function)
        bucket.grant_read(generate_function)
        bucket.grant_read(validate_function)
        bucket.grant_read(render_function)
        bucket.grant_read(download_function)
        bucket.grant_read(workflow_function)
        bucket.grant_read_write(render_function)

        table.grant_read_write_data(upload_function)
        table.grant_read_write_data(workflow_function)
        table.grant_read_write_data(generate_function)
        table.grant_read_write_data(validate_function)
        table.grant_read_write_data(render_function)
        table.grant_read_data(status_function)
        table.grant_read_data(download_function)

        bedrock_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"],
        )
        generate_function.add_to_role_policy(bedrock_policy)

        comprehend_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["comprehend:DetectPiiEntities", "comprehend:DetectKeyPhrases"],
            resources=["*"],
        )
        generate_function.add_to_role_policy(comprehend_policy)
        validate_function.add_to_role_policy(comprehend_policy)

        textract_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["textract:AnalyzeDocument"],
            resources=["*"],
        )

        dynamodb_update_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["dynamodb:UpdateItem"],
            resources=[table.table_arn],
        )

        # Step Functions definition
        parse_resume = tasks.CallAwsService(
            self,
            "ParseResume",
            service="textract",
            action="analyzeDocument",
            iam_resources=["*"],
            parameters={
                "Document": {
                    "S3Object": {
                        "Bucket.$": "$.bucketName",
                        "Name.$": "$.resumeKey",
                    }
                },
                "FeatureTypes": ["TABLES", "FORMS"],
            },
            result_path="$.parsedResume",
        )

        comprehend_task = tasks.CallAwsService(
            self,
            "DetectPII",
            service="comprehend",
            action="detectPiiEntities",
            iam_resources=["*"],
            parameters={
                "Text.$": "$.jobDescription",
                "LanguageCode": "en",
            },
            result_path="$.piiAnalysis",
        )

        generate_task = tasks.LambdaInvoke(
            self,
            "GenerateDraft",
            lambda_function=generate_function,
            payload=sfn.TaskInput.from_object(
                {
                    "tenantId.$": "$.tenantId",
                    "jobId.$": "$.jobId",
                    "resumeKey.$": "$.resumeKey",
                    "jobDescriptionKey.$": "$.jobDescriptionKey",
                    "jobDescription.$": "$.jobDescription",
                    "templateKey.$": "$.templateKey",
                    "parsedResume.$": "$.parsedResume",
                    "piiAnalysis.$": "$.piiAnalysis",
                    "options.$": "$.options",
                }
            ),
            result_path="$.draft",
            payload_response_only=True,
        )

        validate_task = tasks.LambdaInvoke(
            self,
            "ValidateDraft",
            lambda_function=validate_function,
            payload=sfn.TaskInput.from_object(
                {
                    "tenantId.$": "$.tenantId",
                    "jobId.$": "$.jobId",
                    "draft.$": "$.draft",
                    "parsedResume.$": "$.parsedResume",
                    "jobDescription.$": "$.jobDescription",
                }
            ),
            result_path="$.validation",
            payload_response_only=True,
        )

        render_task = tasks.LambdaInvoke(
            self,
            "RenderArtifacts",
            lambda_function=render_function,
            payload=sfn.TaskInput.from_object(
                {
                    "tenantId.$": "$.tenantId",
                    "jobId.$": "$.jobId",
                    "draft.$": "$.draft",
                    "templateKey.$": "$.templateKey",
                }
            ),
            result_path="$.artifacts",
            payload_response_only=True,
        )

        store_task = tasks.CallAwsService(
            self,
            "PersistJobMetadata",
            service="dynamodb",
            action="updateItem",
            iam_resources=[table.table_arn],
            parameters={
                "TableName": table.table_name,
                "Key": {
                    "pk": {"S.$": "States.Format('TENANT#{}', $.tenantId)"},
                    "sk": {"S.$": "States.Format('JOB#{}', $.jobId)"},
                },
                "UpdateExpression": "SET #status = :status, #docx = :docx, #pdf = :pdf, #completedAt = :completedAt, #validation = :validation",
                "ExpressionAttributeNames": {
                    "#status": "status",
                    "#docx": "docxKey",
                    "#pdf": "pdfKey",
                    "#completedAt": "completedAt",
                    "#validation": "validationReport",
                },
                "ExpressionAttributeValues": {
                    ":status": {"S": "COMPLETED"},
                    ":docx": {"S.$": "$.artifacts.docxKey"},
                    ":pdf": {"S.$": "$.artifacts.pdfKey"},
                    ":completedAt": {"S.$": "$.artifacts.completedAt"},
                    ":validation": {"S.$": "States.JsonToString($.validation)"},
                },
            },
            result_path=sfn.JsonPath.DISCARD,
        )

        failure_update = tasks.CallAwsService(
            self,
            "MarkJobFailed",
            service="dynamodb",
            action="updateItem",
            iam_resources=[table.table_arn],
            parameters={
                "TableName": table.table_name,
                "Key": {
                    "pk": {"S.$": "States.Format('TENANT#{}', $.tenantId)"},
                    "sk": {"S.$": "States.Format('JOB#{}', $.jobId)"},
                },
                "UpdateExpression": "SET #status = :status, #error = :error",
                "ExpressionAttributeNames": {
                    "#status": "status",
                    "#error": "error",
                },
                "ExpressionAttributeValues": {
                    ":status": {"S": "FAILED"},
                    ":error": {"S.$": "States.JsonToString($.error)"},
                },
            },
            result_path=sfn.JsonPath.DISCARD,
        ).next(sfn.Fail(self, "WorkflowFailed"))

        comprehend_choice = sfn.Choice(self, "RunComprehend")
        comprehend_choice.when(
            sfn.Condition.boolean_equals("$.options.runComprehend", True),
            comprehend_task.next(generate_task),
        )
        comprehend_choice.otherwise(generate_task)

        generate_task.next(validate_task)
        validate_task.next(render_task)
        render_task.next(store_task)

        chain = sfn.Chain.start(parse_resume).next(comprehend_choice)

        parse_resume.add_catch(failure_update, result_path="$.error")
        generate_task.add_catch(failure_update, result_path="$.error")
        validate_task.add_catch(failure_update, result_path="$.error")
        render_task.add_catch(failure_update, result_path="$.error")
        store_task.add_catch(failure_update, result_path="$.error")

        state_machine = sfn.StateMachine(
            self,
            "ResumeTailorStateMachine",
            definition=chain,
            timeout=Duration.minutes(30),
        )

        state_machine.role.add_to_policy(textract_policy)
        state_machine.role.add_to_policy(comprehend_policy)
        state_machine.role.add_to_policy(dynamodb_update_policy)

        workflow_function.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)

        state_machine.grant_start_execution(workflow_function)

        api = apigateway.RestApi(
            self,
            "ResumeTailorApi",
            rest_api_name="ResumeTailorService",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["*"],
            ),
        )

        upload_jd = api.root.add_resource("uploadJD")
        upload_resume = api.root.add_resource("uploadResume")
        upload_template = api.root.add_resource("uploadTemplate")
        tailor = api.root.add_resource("tailor")
        status_resource = api.root.add_resource("status").add_resource("{jobId}")
        download_resource = api.root.add_resource("download").add_resource("{jobId}")

        upload_integration = apigateway.LambdaIntegration(upload_function)
        workflow_integration = apigateway.LambdaIntegration(workflow_function)
        status_integration = apigateway.LambdaIntegration(status_function)
        download_integration = apigateway.LambdaIntegration(download_function)

        upload_jd.add_method("POST", upload_integration)
        upload_resume.add_method("POST", upload_integration)
        upload_template.add_method("POST", upload_integration)
        tailor.add_method("POST", workflow_integration)
        status_resource.add_method("GET", status_integration)
        download_resource.add_method("GET", download_integration)

        self.api_url = api.url
        self.bucket = bucket
        self.table = table
        self.state_machine = state_machine
