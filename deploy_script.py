import boto3

# Function to get user input
def get_input(prompt):
    return input(prompt).strip()

# Get user inputs
AWS_PROFILE_NAME = get_input("Enter the AWS profile name: ")
REGION = get_input("Enter the AWS region: ")
VPC_ID = get_input("Enter the VPC ID: ")
SUBNET_ID = get_input("Enter the Subnet ID: ")
SECURITY_GROUP_ID = get_input("Enter the Security Group ID: ")
LAMBDA_ROLE_ARN = get_input("Enter the Lambda Role ARN: ")

# Initialize AWS clients with AWS profile
session = boto3.Session(profile_name=AWS_PROFILE_NAME)
apigateway = session.client('apigateway')
ec2 = session.client('ec2')
elbv2 = session.client('elbv2')
lambda_client = session.client('lambda')

# Create Lambda function
lambda_function_name = 'HelloWorldLambda'
lambda_function_code = """
def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': 'Hello world'
    }
"""

response = lambda_client.create_function(
    FunctionName=lambda_function_name,
    Runtime='python3.8',
    Role=LAMBDA_ROLE_ARN,
    Handler='lambda_function.lambda_handler',
    Code={
        'ZipFile': lambda_function_code.encode()
    }
)

lambda_function_arn = response['FunctionArn']

# Create ALB
alb_response = elbv2.create_load_balancer(
    Name='MyALB',
    Subnets=[SUBNET_ID],
    SecurityGroups=[SECURITY_GROUP_ID],
    Scheme='internet-facing',
    Tags=[
        {
            'Key': 'Name',
            'Value': 'MyALB'
        },
    ]
)

alb_arn = alb_response['LoadBalancers'][0]['LoadBalancerArn']

# Create target group for Lambda function
target_group_response = elbv2.create_target_group(
    Name='LambdaTargetGroup',
    Protocol='HTTP',
    Port=80,
    VpcId=VPC_ID,
    TargetType='lambda',
    LambdaFunctionArn=lambda_function_arn
)

target_group_arn = target_group_response['TargetGroups'][0]['TargetGroupArn']

# Create ALB Listener with path-based routing
response = elbv2.create_listener(
    LoadBalancerArn=alb_arn,
    Protocol='HTTP',
    Port=80,
    DefaultActions=[
        {
            'Type': 'fixed-response',
            'FixedResponseConfig': {
                'StatusCode': '404',
                'ContentType': 'text/plain',
                'MessageBody': 'Not Found'
            }
        }
    ]
)

listener_arn = response['Listeners'][0]['ListenerArn']

response = elbv2.create_rule(
    ListenerArn=listener_arn,
    Conditions=[
        {
            'Field': 'path-pattern',
            'Values': ['/testweb*']
        }
    ],
    Priority=1,
    Actions=[
        {
            'Type': 'forward',
            'TargetGroupArn': target_group_arn 
        }
    ]
)

# Create HTTP API in API Gateway
api_response = apigateway.create_rest_api(
    name='MyHTTPAPI',
    description='HTTP API for My Application',
    endpointConfiguration={
        'types': ['EDGE']  
    }
)

api_id = api_response['id']

# Create resource
resource_response = apigateway.create_resource(
    restApiId=api_id,
    parentId=api_response['rootResourceId'],
    pathPart='testweb'
)

# Create method
method_response = apigateway.put_method(
    restApiId=api_id,
    resourceId=resource_response['id'],
    httpMethod='ANY',
    authorizationType='NONE'
)

# Integration
apigateway.put_integration(
    restApiId=api_id,
    resourceId=resource_response['id'],
    httpMethod='ANY',
    type='HTTP_PROXY',  # Using the HTTP_PROXY integration to pass requests directly to the ALB
    integrationHttpMethod='ANY',
    uri=f'http://{alb_arn}/',
)

# Deployment
apigateway.create_deployment(
    restApiId=api_id,
    stageName='prod'
)

print("Deployment is completed. Endpoint available at:")
print(f"https://{api_id}.execute-api.{REGION}.amazonaws.com/prod/testweb")
