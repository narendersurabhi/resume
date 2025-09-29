"""Frontend hosting stack using S3 and CloudFront with dynamic config.json."""
import json
from aws_cdk import (
    RemovalPolicy,
    Stack,
    CfnOutput,
    Fn,
    Duration,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda as lambda_,
    aws_logs as logs,
    custom_resources as cr,
)
from constructs import Construct


class FrontendStack(Stack):
    """Creates resources to host the React single page application."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- S3 bucket for SPA ---
        site_bucket = s3.Bucket(
            self,
            "ResumeFrontendBucket",
            # website_index_document="index.html",   ❌ REMOVE THIS
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # --- CloudFront + OAI ---
        oai = cloudfront.OriginAccessIdentity(self, "ResumeFrontendOAI")
        site_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[site_bucket.arn_for_objects("*")],
                principals=[
                    iam.CanonicalUserPrincipal(
                        oai.cloud_front_origin_access_identity_s3_canonical_user_id
                    )
                ],
            )
        )

        distribution = cloudfront.Distribution(
            self,
            "ResumeFrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            default_root_object="index.html",
        )

        # --- Deploy static frontend build ---
        s3deploy.BucketDeployment(
            self,
            "ResumeFrontendDeployment",
            sources=[s3deploy.Source.asset("frontend/dist")],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # --- Lambda to manage config.json ---
        config_writer = lambda_.Function(
            self,
            "ConfigWriter",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.InlineCode(
                """
import boto3, json, cfnresponse

def handler(event, context):
    try:
        s3 = boto3.client("s3")
        props = event.get("ResourceProperties", {})

        if event["RequestType"] in ["Create", "Update"]:
            config = {
                "apiUrl": props.get("apiUrl"),
                "userPoolId": props.get("userPoolId"),
                "userPoolClientId": props.get("userPoolClientId"),
                "identityPoolId": props.get("identityPoolId"),
                "region": props.get("region"),
                "bucketName": props.get("bucketName"),
            }
            s3.put_object(
                Bucket=props["bucketName"],
                Key="config.json",
                Body=json.dumps(config, indent=2),
                ContentType="application/json"
            )
        elif event["RequestType"] == "Delete":
            try:
                s3.delete_object(Bucket=props["bucketName"], Key="config.json")
            except Exception as e:
                print("Ignore delete error:", str(e))

        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
    except Exception as e:
        print("FAILED", str(e))
        cfnresponse.send(event, context, cfnresponse.FAILED, {})
                """
            ),
            timeout=Duration.minutes(2),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        site_bucket.grant_put(config_writer)

        # Allow CloudFormation to invoke this Lambda
        # config_writer.add_permission(
        #     "AllowCloudFormationInvoke",
        #     principal=iam.ServicePrincipal("cloudformation.amazonaws.com"),
        #     action="lambda:InvokeFunction"
        # )

        # config_writer.grant_invoke(iam.ArnPrincipal(
        #     f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-cfn-exec-role-{self.account}-{self.region}"
        # ))

        # config_writer.grant_invoke(iam.AccountPrincipal(self.account))

        config_writer.add_permission(
            "AllowAllInvoke",
            principal=iam.AnyPrincipal(),
            action="lambda:InvokeFunction"
        )

        config_writer.add_permission(
            "AllowCloudFormationInvoke",
            principal=iam.ServicePrincipal("cloudformation.amazonaws.com"),
            action="lambda:InvokeFunction"
        )


        # site_bucket.grant_read_write(config_writer)
        # config_writer.grant_invoke(iam.ServicePrincipal("lambda.amazonaws.com"))
        # config_writer.grant_invoke(iam.ServicePrincipal("cloudformation.amazonaws.com"))

        # --- Custom resource for lifecycle ---
        cr.AwsCustomResource(
            self,
            "WriteConfigJson",
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": config_writer.function_name,
                    "InvocationType": "Event",
                    "Payload": json.dumps(
                        {
                            "RequestType": "Create",
                            "ResourceProperties": {
                                "apiUrl": Fn.import_value("ResumeApiUrl"),
                                "userPoolId": Fn.import_value("ResumeUserPoolId"),
                                "userPoolClientId": Fn.import_value("ResumeUserPoolClientId"),
                                "identityPoolId": Fn.import_value("ResumeIdentityPoolId"),
                                "region": self.region,
                                "bucketName": site_bucket.bucket_name,
                            },
                        }
                    ),
                },
                physical_resource_id=cr.PhysicalResourceId.of("WriteConfigJsonResource"),
            ),
            on_update=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": config_writer.function_name,
                    "InvocationType": "Event",
                    "Payload": json.dumps(
                        {
                            "RequestType": "Update",
                            "ResourceProperties": {
                                "apiUrl": Fn.import_value("ResumeApiUrl"),
                                "userPoolId": Fn.import_value("ResumeUserPoolId"),
                                "userPoolClientId": Fn.import_value("ResumeUserPoolClientId"),
                                "identityPoolId": Fn.import_value("ResumeIdentityPoolId"),
                                "region": self.region,
                                "bucketName": site_bucket.bucket_name,
                            },
                        }
                    ),
                },
                physical_resource_id=cr.PhysicalResourceId.of("WriteConfigJsonResource"),
            ),
            on_delete=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": config_writer.function_name,
                    "InvocationType": "Event",
                    "Payload": json.dumps(
                        {
                            "RequestType": "Delete",
                            "ResourceProperties": {
                                "bucketName": site_bucket.bucket_name,
                            },
                        }
                    ),
                },
                physical_resource_id=cr.PhysicalResourceId.of("WriteConfigJsonResource"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[config_writer.function_arn]
            ),
        )

        # --- Outputs ---
        CfnOutput(self, "CloudFrontDomain", value=distribution.distribution_domain_name)
        CfnOutput(self, "FrontendBucket", value=site_bucket.bucket_name)
        CfnOutput(self, "ConfigFile", value="config.json")
