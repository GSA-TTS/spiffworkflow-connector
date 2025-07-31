**SpiffWorkflow Service Connector**
=====================================

This repository contains a V2 (simplified) implementation of SpiffWorkflow's Service Connector Proxy. Specifically, it embeds a service connector extension called `PDFtoS3` that generates a PDF from a template and uploads it to an S3 bucket.

**Overview**
------------

The `PDFtoS3` class takes in a template name, data, and S3 bucket information, and generates a PDF using the Playwright library. It then uploads the PDF to the specified S3 bucket using either a Minio client (for development) or an S3 client (for production).

**Features**
------------

* Generate PDFs from templates using Jinja2
* Upload PDFs to S3 buckets using Minio or S3 clients
* Supports development and production environments
* Returns a JSON response with upload result, including object URL, bucket name, and object name

**Requirements**
---------------

* Python 3.12+
* Playwright library
* Jinja2 library
* Minio client (for development)
* S3 client (for production)
* S3 bucket credentials

**Usage**
-----

1. Install the required libraries using `pip install -r requirements.txt`
2. Create an instance of the `PDFtoS3` class, passing in the required parameters (bucket name, object name, template name, headers, and test data)
3. Call the `execute` method to generate the PDF and upload it to S3
4. Handle the JSON response returned by the `execute` method

**Example**
-------

Assuming the service is running on http://localhost:5000 and accepts JSON payloads, you can use the following curl command to hit the service:

```bash
curl -X POST \
  http://localhost:8200/v1/do/pdf/pdf_to_s3 \
  -H 'Content-Type: application/json' \
  -d '{
        "bucket": "testbucket",
        "object_name": "$YOUR_OBJECT_NAME",
        "template_name": "$YOUR_TEMPLATE_NAME",
        "headers": "{\"AWS_ACCESS_KEY_ID\": \"$YOUR_AWS_ACCESS_KEY_ID\", \"AWS_SECRET_ACCESS_KEY\": \"$YOUR_AWS_SECRET_ACCESS_KEY\", \"AWS_DEFAULT_REGION\": \"us-gov-west-1\"}",
        "test_data": {
          "key": "value"
        }
      }'
```
This will send a JSON payload to the service, which will generate a PDF and upload it to the specified S3 bucket.

**NOTES:**
- Your template name must be a template that is present in `/templates` directory.
- Ideally, your test_data dict represents keys that are present in the Jinja template you supplied above.

### Using the local Minio client

To use the Minio client, you need to modify your headers string to be:

```bash
	"headers": "{\"ENDPOINT_URL\": \"http://minio:9000\", \"AWS_ACCESS_KEY_ID\": \"minioadmin_key\", \"AWS_SECRET_ACCESS_KEY\":\"minioadmin_secret\", \"AWS_DEFAULT_REGION\": \"us-east-1\"}",
```

Adding the extra ENDPOINT_URL string will cause Boto to utilize the local Minio container rather than defaulting to actual S3.

**Development**
--------------

To develop and test this repository, you can run `make` in a shell which will build and start the local docker network.

**Contributing**
------------

Contributions are welcome! Please submit a pull request with your changes, and ensure that you have tested your code thoroughly.

**License**
-------

This repository is licensed under the [MIT License](https://opensource.org/licenses/MIT).
