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
        
    # Check if we can access the file via presigned URL
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

echo -e "${GREEN}All tests passed successfully.${NC}"

echo -e "\n${GREEN}All tests completed.${NC}"
