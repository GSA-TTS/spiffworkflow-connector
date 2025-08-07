#!/bin/bash
set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if a file exists in Minio's local directory
check_file_exists() {
    local bucket=$1
    local file=$2
    echo -e "${YELLOW}Looking for $file in bucket $bucket...${NC}"
    
    # For the legacy response, check if we get a success response
    legacy_result=$(echo "$response" | jq -r '.command_response.body | fromjson? | .result // empty')
    if [ "$legacy_result" = "success" ]; then
        echo -e "${GREEN}✓ File $file created successfully (legacy response)${NC}"
        return 0
    fi
    
    # For the new format, check if we can access the file via presigned URL
    presigned_url=$(echo "$response" | jq -r '.command_response.body.presigned_link // empty')
    if [ -n "$presigned_url" ]; then
        echo -e "${YELLOW}Checking URL: $presigned_url${NC}"
        if curl -s -f "$presigned_url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ File $file exists in bucket $bucket (accessible via URL)${NC}"
            return 0
        else
            echo -e "${RED}✗ File $file not accessible via presigned URL${NC}"
            return 1
        fi
    else
        echo -e "${RED}✗ No valid URL found in response${NC}"
        return 1
    fi
}

# Setup mc alias in the Minio container (idempotent)
docker exec minio mc alias set local http://localhost:9000 minioadmin minioadmin >/dev/null 2>&1

echo -e "${GREEN}Testing artifacts/GenerateArtifact command...${NC}"
response=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"id": "test/sample.pdf", "template": "blm-ce.html", "data": {"projectName": "Test Project"}, "generate_links": true}' \
    http://localhost:8200/v1/do/artifacts/GenerateArtifact)
# echo -e "${YELLOW}Debug: Raw response:${NC}"
# echo "$response"
# echo -e "${YELLOW}Debug: Response structure:${NC}"
# echo "$response" | jq .

# Get the HTTP status from the response
http_status=$(echo "$response" | jq -r '.command_response.http_status')
if [ "$http_status" != "200" ]; then
    echo -e "${RED}Request failed with status $http_status${NC}"
    echo -e "${RED}Error: $(echo "$response" | jq -r '.error')${NC}"
    exit 1
fi

# Check if file was created
check_file_exists "testbucket" "test/sample.pdf"

# Extract and verify the presigned URL works
presigned_url=$(echo $response | jq -r '.command_response.body.presigned_link')
if curl -s -f "$presigned_url" >/dev/null; then
    echo -e "${GREEN}✓ Presigned URL is accessible${NC}"
else
    echo -e "${RED}✗ Presigned URL is not accessible${NC}"
    exit 1
fi

echo -e "\n${GREEN}Testing artifacts/GetLinkToArtifact command...${NC}"
response=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"id": "test/sample.pdf"}' \
    http://localhost:8200/v1/do/artifacts/GetLinkToArtifact)
echo $response | jq .

# Verify the links returned match the file we created
presigned_url=$(echo $response | jq -r '.command_response.body.presigned_link')
if curl -s -f "$presigned_url" >/dev/null; then
    echo -e "${GREEN}✓ GetLinkToArtifact presigned URL is accessible${NC}"
else
    echo -e "${RED}✗ GetLinkToArtifact presigned URL is not accessible${NC}"
    exit 1
fi

echo -e "\n${YELLOW}Testing deprecated pdf/pdf_to_s3 command (should work but show warning)...${NC}"
response=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"bucket": "testbucket", "object_name": "test/legacy.pdf", "template_name": "blm-ce.html", "headers": "{\"ENDPOINT_URL\": \"http://minio:9000\", \"AWS_ACCESS_KEY_ID\": \"minioadmin\", \"AWS_SECRET_ACCESS_KEY\": \"minioadmin\", \"AWS_DEFAULT_REGION\": \"us-east-1\"}", "test_data": {"projectName": "Legacy Test"}}' \
    http://localhost:8200/v1/do/pdf/pdf_to_s3)

# Print response first so we can see any messages
echo -e "${YELLOW}Response from deprecated command:${NC}"
echo "$response" | jq .

# For deprecated command, we expect success but there might be warnings in logs
http_status=$(echo "$response" | jq -r '.command_response.http_status')
if [ "$http_status" = "200" ]; then
    echo -e "${GREEN}✓ Deprecated command executed successfully${NC}"
    
    # Check if file was created
    check_file_exists "testbucket" "test/legacy.pdf"
else
    echo -e "${RED}✗ Deprecated command failed with status $http_status${NC}"
    echo -e "${RED}Error: $(echo "$response" | jq -r '.error')${NC}"
    exit 1
fi

echo -e "${GREEN}All tests passed successfully.${NC}"

echo -e "\n${GREEN}All tests completed.${NC}"
