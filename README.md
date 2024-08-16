
# Terminology_mapping

Setting up this terminology server needs three major steps. 

# 1.  Setting Up Snowstorm Server

## Getting Started

1. Download or clone the repository from [IHTSDO/snowstorm](https://github.com/IHTSDO/snowstorm): Scalable SNOMED CT Terminology Server using Elasticsearch.
2. Install Docker and Docker Compose.
3. Set the `vm.max_map_count` to `262144` by running the following command:
   ```bash
   wsl -d docker-desktop sysctl -w vm.max_map_count=262144

## STARTING SNOWSTORM
1. Navigate to the directory where you cloned the repository.

2. Run the following command to start the Snowstorm server:
    ```bash
    docker-compose up -d

3. The Snowstorm server will start and be accessible at http://localhost:8080 by default.

## Uploading the Terminology
1. Once the Snowstorm server is set up, navigate to the Swagger UI at http://localhost:8080.

2. Under the Import Section, create a new import by POSTing the following JSON:
    ```JSON
        {
            "branchPath": "MAIN",
            "createCodeSystemVersion": true,
             "type": "SNAPSHOT"
        }

3. Click "Execute" and note the generated ID (e.g., d7937fe9-04df-4516-af5d-967a42f3e280).

4. Use this ID to upload the terminology at imports/<import_id>/archive on the UI. Enter the ID, upload the zip file, and click "Execute".

## Retrieving SNOMED Concepts
### Retrieving a SNOMED Concept by Identifier

Use the following URL format to retrieve all information about a concept, including its different terms/synonyms:

    http://localhost:8080/browser/MAIN/concepts/<concept_id>

### Retrieving a SNOMED Concept by Term
Use this URL format to search for different concepts by keyword. It returns the concept code for all concepts related to the keyword:

    http://localhost:8080/MAIN/concepts?term=<name>


### Performing ECL Queries
Perform Expression Constraint Language (ECL) queries and get their outputs through HTTP requests:

    http://localhost:8080/MAIN/concepts?ecl=<ecl_query>

### Mapping SNOMED to ICD-10
Use this URL format to retrieve the ICD-10 reference set to get the ICD-10 codes for a particular snomed concept

    http://localhost:8080/MAIN/members?referenceSet=447562003&referencedComponentId=<concept_id>

## References

    https://github.com/IHTSDO/snowstorm

    https://github.com/IHTSDO/snowstorm/blob/master/docs/loading-snomed.md#via-rest

    https://github.com/IHTSDO/snowstorm/blob/master/docs/updating-snomed-and-extensions.md

    https://github.com/IHTSDO/snowstorm/blob/master/docs/using-the-api.md

    https://github.com/IHTSDO/snowstorm/blob/master/docs/getting-started.md




# 2.  Setting Up Llama3 using Ollama

Visit https://ollama.com/ and download and  install the Ollama application

To verify that Ollama is running, open your browser and go to:
    http://localhost:11434

At this point, Ollama is running, but we need to install an LLM. Let’s pull and run Llama3

    
    ollama pull llama3
    ollama run llama3

With this Llama3 should be running on your local machine. Once you run Llama3 you can interact with in through command line as well.

# 3.  Installing Fast API and running our code 

1. Install FastAPI and Uvicorn

    pip install fastapi uvicorn

2. Run the FastAPI Application using the command   

    uvicorn terminology_mapping_with_API:app --reload

3. Once your server is running, you can test the API using tools like Postman or curl, or by visiting http://127.0.0.1:8000/docs in your browser. FastAPI automatically generates interactive API documentation.

4. Post the following on http://127.0.0.1:8000/get_snomed_code adding your diagnostic term as given.

        {
            "diagnosis_type": "Medical diagnosis",
            "diagnostic_term": "Urinary  incontinent"
        }

5. You must find an output in the following format:

    {
    "results": [
        {
            "term": "Urinary  incontinent",
            "system ": "SNOMED CT",
            "code ": "165232002",
            "text": "Urinary incontinence (finding)",
            "Retrival Method": "Used Llama3 to get the term",
            "url": "https://browser.ihtsdotools.org/?perspective=full&conceptId1=165232002&edition=MAIN/2024-08-01&release=&languages=en",
            "ICD10_code": "R32",
            "Mapping_advice": "ALWAYS R32"
        }
    ]
}







