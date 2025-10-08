"""Frontend hosting stack using S3 and CloudFront with dynamic config.json and export validation."""
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
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- S3 bucket for SPA (private, OAI access only) ---
        site_bucket = s3.Bucket(
            self,
            "ResumeFrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- OAI and bucket policy (read via CloudFront only) ---
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
        # Deny non-TLS
        site_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:GetObject"],
                resources=[site_bucket.arn_for_objects("*")],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )

        # --- CloudFront distribution (S3 origin, SPA fallbacks) ---
        distribution = cloudfront.Distribution(
            self,
            "ResumeFrontendDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
            ],
        )

        # --- Lambda that writes config.json to S3 from live exports ---
        config_writer = lambda_.Function(
            self, "ConfigWriter",
            runtime=lambda_.Runtime.PYTHON_3_9,   # <= 3.9, not 3.11
            handler="index.handler",
            timeout=Duration.minutes(2),
            log_retention=logs.RetentionDays.ONE_WEEK,
            code=lambda_.InlineCode(
    """import json, boto3, os, logging
log = logging.getLogger(); log.setLevel(logging.INFO)

def handler(event, context):
    # event is from AwsCustomResource -> Lambda.Invoke
    props = event.get("ResourceProperties") or {}
    bucket = props.get("bucketName")
    cfg = {
        "apiUrl": props.get("apiUrl"),
        "userPoolId": props.get("userPoolId"),
        "userPoolClientId": props.get("userPoolClientId"),
        "identityPoolId": props.get("identityPoolId"),
        "region": props.get("region"),
        "bucketName": bucket,
    }
    body = json.dumps(cfg, indent=2)
    log.info("Writing config.json to %s", bucket)
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key="config.json",
        Body=body.encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache",
    )
    return {"ok": True, "len": len(body)}
    """
            ),
        )
        site_bucket.grant_put(config_writer)

        # site_bucket.grant_read_write(config_writer)
        
        config_writer.add_permission(
            "AllowCloudFormationInvoke",
            principal=iam.ServicePrincipal("cloudformation.amazonaws.com"),
            action="lambda:InvokeFunction",
        )
        config_writer.add_permission(  # optional broad invoke
            "AllowAllInvoke",
            principal=iam.AnyPrincipal(),
            action="lambda:InvokeFunction",
        )        

        # --- Deploy SPA assets and invalidate CloudFront ---
        deploy = s3deploy.BucketDeployment(
            self, "FrontendDeploy",
            sources=[s3deploy.Source.asset("frontend/dist", exclude=["config.json"])],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )
        deploy.node.add_dependency(distribution)

        write_cfg = cr.AwsCustomResource(
            self, "WriteConfigJson",
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": config_writer.function_name,
                    "InvocationType": "Event",
                    "Payload": json.dumps({
                        "RequestType": "Create",
                        "ResourceProperties": {
                            "apiUrl": Fn.import_value("ResumeApiUrl"),
                            "userPoolId": Fn.import_value("ResumeUserPoolId"),
                            "userPoolClientId": Fn.import_value("ResumeUserPoolClientId"),
                            "identityPoolId": Fn.import_value("ResumeIdentityPoolId"),
                            "region": self.region,
                            "bucketName": site_bucket.bucket_name,
                        }
                    }),
                },
                physical_resource_id=cr.PhysicalResourceId.of("WriteConfigJsonResource"),
            ),
            on_update=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={  # same as above, RequestType "Update"
                    "FunctionName": config_writer.function_name,
                    "InvocationType": "Event",
                    "Payload": json.dumps({
                        "RequestType": "Update",
                        "ResourceProperties": {
                            "apiUrl": Fn.import_value("ResumeApiUrl"),
                            "userPoolId": Fn.import_value("ResumeUserPoolId"),
                            "userPoolClientId": Fn.import_value("ResumeUserPoolClientId"),
                            "identityPoolId": Fn.import_value("ResumeIdentityPoolId"),
                            "region": self.region,
                            "bucketName": site_bucket.bucket_name,
                        }
                    }),
                },
                physical_resource_id=cr.PhysicalResourceId.of("WriteConfigJsonResource"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE  # keep simple
            ),
        )
        write_cfg.node.add_dependency(deploy)

        # --- Outputs ---
        CfnOutput(self, "CloudFrontDomain", value=distribution.distribution_domain_name)
        CfnOutput(self, "FrontendBucket", value=site_bucket.bucket_name)
        CfnOutput(self, "ConfigFile", value="config.json")
