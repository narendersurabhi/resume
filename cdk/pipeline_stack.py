"""Automated CI/CD pipeline for building and deploying the resume application."""
from aws_cdk import (
    CfnOutput,
    CfnParameter,
    Duration,
    RemovalPolicy,
    Stack,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as cpactions,
    aws_codestarconnections as codestarconnections,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct


class PipelineStack(Stack):
    """Defines the push-triggered CodePipeline v2 with CodeBuild deployment stage."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        repo_owner = CfnParameter(
            self,
            "RepositoryOwner",
            type="String",
            default="userprofiles",
            description="GitHub organization or user that owns the source repository.",
        )

        repo_name = CfnParameter(
            self,
            "RepositoryName",
            type="String",
            default="resume",
            description="GitHub repository name containing the application source.",
        )

        branch_name = CfnParameter(
            self,
            "RepositoryBranch",
            type="String",
            default="main",
            description="Git branch that should trigger the pipeline when updated.",
        )

        connection_name = CfnParameter(
            self,
            "ConnectionName",
            type="String",
            default="resume-github-connection",
            description="Friendly name for the CodeConnections GitHub connection.",
        )

        pipeline_name = CfnParameter(
            self,
            "PipelineName",
            type="String",
            default="ResumeApplicationPipeline",
            description="Name for the AWS CodePipeline v2 pipeline.",
        )

        download_repo = ecr.Repository.from_repository_name(
            self, "PipelineDownloadRepo", "resume-download"
        )
        generate_repo = ecr.Repository.from_repository_name(
            self, "PipelineGenerateRepo", "resume-generate"
        )
        upload_repo = ecr.Repository.from_repository_name(
            self, "PipelineUploadRepo", "resume-upload"
        )

        connection = codestarconnections.CfnConnection(
            self,
            "GitHubConnection",
            connection_name=connection_name.value_as_string,
            provider_type="GitHub",
        )

        artifact_bucket = s3.Bucket(
            self,
            "PipelineArtifacts",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            auto_delete_objects=False,
            removal_policy=RemovalPolicy.RETAIN,
        )

        codebuild_role = iam.Role(
            self,
            "CodeBuildServiceRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        log_group_arn = f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/codebuild/*"

        codebuild_policy = iam.Policy(
            self,
            "CodeBuildInlinePolicy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:DescribeLogStreams",
                        "logs:PutLogEvents",
                    ],
                    resources=[log_group_arn, f"{log_group_arn}:*"]
                ),
                iam.PolicyStatement(
                    actions=["sts:AssumeRole"],
                    resources=[
                        f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-deploy-role-{self.account}-{self.region}",
                        f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-file-publishing-role-{self.account}-{self.region}",
                        f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-image-publishing-role-{self.account}-{self.region}",
                        f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-lookup-role-{self.account}-{self.region}",
                    ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:BatchGetImage",
                        "ecr:CompleteLayerUpload",
                        "ecr:DescribeImages",
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:InitiateLayerUpload",
                        "ecr:PutImage",
                        "ecr:UploadLayerPart",
                    ],
                    resources=[
                        download_repo.repository_arn,
                        generate_repo.repository_arn,
                        upload_repo.repository_arn,
                    ],
                ),
                iam.PolicyStatement(
                    actions=["ecr:GetAuthorizationToken"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "s3:GetObject",
                        "s3:GetObjectVersion",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket",
                        "s3:GetBucketVersioning",
                    ],
                    resources=[artifact_bucket.bucket_arn, f"{artifact_bucket.bucket_arn}/*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "s3:GetObject",
                        "s3:GetObjectVersion",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket",
                        "s3:GetBucketVersioning",
                    ],
                    resources=[
                        f"arn:aws:s3:::cdk-hnb659fds-assets-{self.account}-{self.region}",
                        f"arn:aws:s3:::cdk-hnb659fds-assets-{self.account}-{self.region}/*",
                    ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "cloudformation:CreateChangeSet",
                        "cloudformation:DeleteChangeSet",
                        "cloudformation:DescribeChangeSet",
                        "cloudformation:DescribeStackEvents",
                        "cloudformation:DescribeStacks",
                        "cloudformation:ExecuteChangeSet",
                        "cloudformation:GetTemplate",
                        "cloudformation:ListStackResources",
                        "cloudformation:ListStacks",
                        "cloudformation:UpdateStack",
                        "cloudformation:CreateStack",
                        "cloudformation:DeleteStack",
                        "cloudformation:TagResource",
                        "cloudformation:UntagResource",
                        "cloudformation:ValidateTemplate",
                    ],
                    resources=[
                        f"arn:aws:cloudformation:{self.region}:{self.account}:stack/Resume*/*",
                        f"arn:aws:cloudformation:{self.region}:{self.account}:stack/CDKToolkit/*",
                    ],
                ),
                iam.PolicyStatement(
                    actions=["iam:PassRole"],
                    resources=[
                        f"arn:aws:iam::{self.account}:role/cdk-*",
                        f"arn:aws:iam::{self.account}:role/Resume*",
                    ],
                    conditions={
                        "StringEquals": {
                            "iam:PassedToService": [
                                "cloudformation.amazonaws.com",
                                "lambda.amazonaws.com",
                            ]
                        }
                    },
                ),
                iam.PolicyStatement(
                    actions=["sts:GetCallerIdentity"],
                    resources=["*"],
                ),
            ],
        )

        codebuild_policy.attach_to_role(codebuild_role)

        project = codebuild.PipelineProject(
            self,
            "ResumeCodeBuildProject",
            role=codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=True,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yml"),
            timeout=Duration.hours(1),
            environment_variables={
                "DOWNLOAD_REPO": codebuild.BuildEnvironmentVariable(value=download_repo.repository_name),
                "GENERATE_REPO": codebuild.BuildEnvironmentVariable(value=generate_repo.repository_name),
                "UPLOAD_REPO": codebuild.BuildEnvironmentVariable(value=upload_repo.repository_name),
            },
        )

        artifact_bucket.grant_read_write(project)

        pipeline_role = iam.Role(
            self,
            "PipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
        )

        pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                    "s3:GetBucketVersioning",
                ],
                resources=[artifact_bucket.bucket_arn, f"{artifact_bucket.bucket_arn}/*"],
            )
        )
        pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "codebuild:BatchGetBuilds",
                    "codebuild:StartBuild",
                    "codebuild:BatchGetBuildBatches",
                    "codebuild:StartBuildBatch",
                ],
                resources=[project.project_arn],
            )
        )
        pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[codebuild_role.role_arn],
                conditions={
                    "StringEquals": {"iam:PassedToService": "codebuild.amazonaws.com"}
                },
            )
        )
        pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["codestar-connections:UseConnection"],
                resources=[connection.attr_connection_arn],
            )
        )

        pipeline = codepipeline.Pipeline(
            self,
            "ResumePipeline",
            pipeline_name=pipeline_name.value_as_string,
            artifact_bucket=artifact_bucket,
            cross_account_keys=False,
            pipeline_type=codepipeline.PipelineType.V2,
            role=pipeline_role,
        )

        source_output = codepipeline.Artifact("SourceOutput")

        pipeline.add_stage(
            stage_name="Source",
            actions=[
                cpactions.CodeStarConnectionsSourceAction(
                    action_name="GitHubSource",
                    connection_arn=connection.attr_connection_arn,
                    owner=repo_owner.value_as_string,
                    repo=repo_name.value_as_string,
                    branch=branch_name.value_as_string,
                    output=source_output,
                    trigger_on_push=True,
                )
            ],
        )

        pipeline.add_stage(
            stage_name="Build",
            actions=[
                cpactions.CodeBuildAction(
                    action_name="BuildAndDeploy",
                    project=project,
                    input=source_output,
                )
            ],
        )

        CfnOutput(
            self,
            "PipelineNameOutput",
            value=pipeline.pipeline_name,
            description="Name of the created CodePipeline.",
        )
        CfnOutput(
            self,
            "ConnectionArnOutput",
            value=connection.attr_connection_arn,
            description="CodeConnections ARN that must be authorized in the AWS console.",
        )
        CfnOutput(
            self,
            "CodeBuildProjectName",
            value=project.project_name,
            description="Name of the CodeBuild project used by the pipeline.",
        )
