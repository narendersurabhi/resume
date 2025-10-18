FROM public.ecr.aws/lambda/python:3.12

# Install Python dependencies into /opt/python so they are available on the Lambda path
COPY requirements.txt ./
RUN pip install -r requirements.txt --target "/opt/python"

# Copy application code and schema
COPY app.py ${LAMBDA_TASK_ROOT}/
COPY schema.json ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]

