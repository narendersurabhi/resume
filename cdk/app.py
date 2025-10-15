#!/usr/bin/env python3
from aws_cdk import App, Environment

from .frontend_stack import FrontendStack
from .backend_stack import BackendStack
from .pipeline_stack import PipelineStack
from .auth_stack import AuthStack

app = App()

env = Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region"),
)

auth_stack = AuthStack(app, "ResumeAuthStack", env=env)
backend_stack = BackendStack(app, "ResumeBackendStack", env=env)
frontend_stack = FrontendStack(app, "ResumeFrontendStack", env=env)

# Gate pipeline creation behind a context flag to avoid self-updates by default
deploy_pipeline_ctx = app.node.try_get_context("deployPipeline")
deploy_pipeline = False
if isinstance(deploy_pipeline_ctx, str):
    deploy_pipeline = deploy_pipeline_ctx.lower() in ("1", "true", "yes")
elif isinstance(deploy_pipeline_ctx, bool):
    deploy_pipeline = deploy_pipeline_ctx

pipeline_stack = None
if deploy_pipeline:
    pipeline_stack = PipelineStack(app, "ResumePipelineStack", env=env)

# Frontend relies on exports from Auth + Backend
frontend_stack.add_dependency(auth_stack)
frontend_stack.add_dependency(backend_stack)

# Ensure pipeline is created after foundational stacks are defined
if pipeline_stack is not None:
    pipeline_stack.add_dependency(frontend_stack)

app.synth()
