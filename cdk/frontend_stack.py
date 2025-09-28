"""Frontend hosting stack using S3 and CloudFront."""
import json
from aws_cdk import RemovalPolicy, Stack, CfnOutput
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

from aws_cognito_identitypool_alpha import IdentityPool
from aws_cdk import aws_cognito as cognito


class FrontendStack(Stack):
    """Creates resources to host the React single page application."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_url: str,
        user_pool: cognito.UserPool,
        identity_pool: IdentityPool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        site_bucket = s3.Bucket(
            self,
            "ResumeFrontendBucket",
            website_index_document="index.html",
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        oai = cloudfront.OriginAccessIdentity(self, "ResumeFrontendOAI")
        site_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[site_bucket.arn_for_objects("*")],
                principals=[iam.CanonicalUserPrincipal(oai.cloud_front_origin_access_identity_s3_canonical_user_id)],
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

        runtime_config = {
            "apiUrl": api_url,
            "userPoolId": user_pool.user_pool_id,
            "userPoolClientId": user_pool.user_pool_client_id,
            "identityPoolId": identity_pool.identity_pool_id,
            "region": self.region,
            "bucketName": site_bucket.bucket_name,
        }

        s3deploy.BucketDeployment(
            self,
            "ResumeFrontendDeployment",
            sources=[
                s3deploy.Source.asset("frontend/dist"),
                s3deploy.Source.data(
                    "config.json",
                    json.dumps(runtime_config, indent=2),
                ),
            ],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        CfnOutput(self, "CloudFrontDomain", value=distribution.distribution_domain_name)
        CfnOutput(self, "FrontendBucket", value=site_bucket.bucket_name)
        CfnOutput(self, "RuntimeConfig", value="config.json")
