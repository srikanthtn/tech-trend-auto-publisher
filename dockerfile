FROM public.ecr.aws/lambda/python:3.11

# Set working directory to the Lambda task root
WORKDIR ${LAMBDA_TASK_ROOT}

# Install Python dependencies first (leverages Docker cache)
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy function code into the Lambda task root
COPY lambda_pipeline.py ${LAMBDA_TASK_ROOT}/

# (Optional) copy other local modules if you have them
# COPY some_module.py ${LAMBDA_TASK_ROOT}/

# Set the Lambda handler (module.function)
CMD ["lambda_pipeline.lambda_handler"]

