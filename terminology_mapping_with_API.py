from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

import requests
import re
import wordsegment
import subprocess
from spellchecker import SpellChecker

wordsegment.load()
name_concept_mapping = dict()

def segment_compound_word(compound_word):
    segmented_words = wordsegment.segment(compound_word)
    if len(segmented_words) > 1:
        if 's' in segmented_words:
            segmented_words.remove('s')
        return ' '.join(segmented_words)
    else:
        return compound_word
    
#Corrects spelling of the words
def correct_text(text):
    spell = SpellChecker()
    words = text.split()
    corrected_text = []
    for word in words:
        corrected_word = spell.correction(word)
        corrected_text.append(corrected_word)
    if None in corrected_text:
        return None
    return ' '.join(corrected_text)

def retrieve_ICD10_code_and_advice(code):
    url = f"http://localhost:8080/MAIN/members?referenceSet=447562003&referencedComponentId={code}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            target_component_id = str(code)
            items = data.get('items', [])
            for item in items:
                if item.get('referencedComponentId') == target_component_id:
                    print("yes")
                    additional_fields = item.get('additionalFields', {})
                    map_target = additional_fields.get('mapTarget')
                    map_advice = additional_fields.get('mapAdvice') 
                    return(map_target,map_advice)
    except Exception as e:
        print(f"Error fetching display name from Snowstorm server: {e}")
    return None,None

# This function checks if the concept is active or not
def is_concept_active(code):
    url = f"http://localhost:8080/browser/MAIN/concepts/{code}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get('active', False):
                return True
            else:
                return False
    except Exception as e:
        print(f"Error fetching display name from Snowstorm server: {e}")
    return []

#This function gets all the active synonyms for a particular concept
def get_display_name_from_snowstorm(code):
    url = f"http://localhost:8080/browser/MAIN/concepts/{code}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            # Initialize an empty list to store the terms
            descriptions = []
            # Iterate over each dictionary in the 'descriptions' list
            for desc in data.get('descriptions', []):
                # Check if the 'active' field is True
                if desc.get('active', False):
                    # Get the value of the 'term' key, defaulting to an empty string if not present
                    term = desc.get('term', '')
                    # Append the term to the 'descriptions' list
                    descriptions.append(term)
            return descriptions
    except Exception as e:
        print(f"Error fetching display name from Snowstorm server: {e}")
    return []

#this function checks whether the concept is a finding or disorder type
def check_fsn_type(code):
    url = f"http://localhost:8080/browser/MAIN/concepts/{code}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            concept = data["fsn"]["term"]
            if "(disorder)" in concept or "(finding)" in concept:
                return True
            return False
    except Exception as e:
        print(f"Error fetching display name from Snowstorm server: {e}")
    return []

def get_fsn_name(code):
    url = f"http://localhost:8080/browser/MAIN/concepts/{code}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            concept = data["fsn"]["term"]
            return concept
    except Exception as e:
        print(f"Error fetching display name from Snowstorm server: {e}")
    return None

def run_ollama_medllama2(query):
    try:
        command = ['ollama', 'run', 'llama3', '--', query]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True, encoding='utf-8')
        if result.returncode != 0:
            print("Error running the command:", result.stderr)
            return None
        return result.stdout.strip()
    except Exception as e:
        print("An error occurred:", e)
        return None

#This function gets me the code we search for the term on snowstorm
def get_concept_id(name):
    url = f"http://localhost:8080/MAIN/concepts?term={name}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            matched_concepts = []
            synonym_concept_mapping = {}

            if data['total'] != 0:
                # First pass: Check FSNs and collect potential matches
                for item in data['items']:
                    if 'fsn' in item and 'term' in item['fsn']:
                        fsn_term = re.sub(r'\(.*?\)', '', item['fsn']['term'].lower())
                        if check_fsn_type(item['conceptId']) and item['active']:
                            matched_concepts.append((fsn_term, item['conceptId']))
                            if name.lower() == fsn_term:
                                return item['conceptId']
    
                # Second pass: Check synonyms if FSN did not match exactly
                for item in data['items']:
                    if check_fsn_type(item['conceptId']) and item['active']:
                        synonyms = get_display_name_from_snowstorm(item['conceptId'])
                        for synonym in synonyms:
                            synonym_term = synonym.lower()
                            synonym_concept_mapping[synonym_term] = item['conceptId']
                            if name.lower() == synonym_term:
                                return item['conceptId']
    
                # Third pass: Check if the name is a subset of any synonyms
                for synonym_term, concept_id in synonym_concept_mapping.items():
                    if name.lower() in synonym_term:
                        return concept_id

                # Send only FSN names to Llama for semantic comparison if no synonym matches
                fsn_list = [fsn for fsn, _ in matched_concepts]
                query = f"Which of these FSN terms is the closest in meaning to '{name}': {', '.join(fsn_list)}? Provide the answer in the format (in ['']) ['closest term'] or ['None']."
                print(query)
                result = run_ollama_medllama2(query)
                print(result)
                    
               # Parse the result to find the closest FSN or None
                print(matched_concepts)
                match = re.search(r"\['(.*?)'\]", result)
                if match:
                    closest_term = match.group(1).strip().lower()
                    print(closest_term)
                    if closest_term != "none":
                        # Find the concept ID corresponding to the closest FSN term
                        for fsn_term, concept_id in matched_concepts:
                            if closest_term == fsn_term.strip():
                                return concept_id
                    
                # If Llama returns 'None' or no match is found, return None
                print("none")
                return None
        else:
            print(f"Concept ID not found for diagnostic name '{name}'")
            return None
    except Exception as e:
        print(f"Error fetching concept ID from Snowstorm server: {e}")
        return None

#check if a name is present in the synonyms
def is_display_name_present(corrected_name, display_names):
    for name in display_names:
        if name.lower() in corrected_name.lower():
            return True
    return False

# Function to extract terms from medllama2 output
def extract_terms_from_medllama_output(output):
    match = re.search(r"\[.*?\]", output)
    if match:
        terms_str = match.group(0)
        terms = [term.strip().strip("'\"") for term in terms_str[1:-1].split(",")]
        return terms
    else:
        lines = output.split('\n')
        terms = []
        for line in lines:
            line = line.strip()
            if line.startswith('*') or line.startswith('•'):
                term = line.lstrip('*•').strip()
                terms.append(term)
        return terms

def find_code(corrected_name):
    concept_id = get_concept_id(corrected_name)
    if concept_id is None:
        word = re.sub(r'\s+', '', corrected_name)
        if word != corrected_name:
            concept_id = get_concept_id(word.lower())
    if concept_id is None:
        word = segment_compound_word(corrected_name.lower())
        concept_id = get_concept_id(word.lower())
    if concept_id:
        synonyms = get_display_name_from_snowstorm(concept_id)
        name_concept_mapping[corrected_name.lower()] = concept_id
        for synonym in synonyms:
            name_concept_mapping[synonym.lower()] = concept_id
        return (concept_id, "Diagnosis found from SNOMED")
    else:
        query = (
            f"Only provide me the primary disease or condition terms/expand medical abbreviations without any conjunctions or descriptive qualifiers. "
            f"If no corrections are needed, return the input as a single term. "
            f"Provide the corrected term in the format ['corrected_term']. "
            f"Diagnosis: '{corrected_name}'"
        )
        print(query)
        medllama_output = run_ollama_medllama2(query)
        print(medllama_output)
        if medllama_output:
            corrected_terms = extract_terms_from_medllama_output(medllama_output)
            print(corrected_terms)
            if corrected_terms:
                snowstorm_results = []
                for term in corrected_terms:
                    snomed_result = get_concept_id(term)
                    if snomed_result:
                        snowstorm_results.append(snomed_result)
                filtered_results = [res for res in snowstorm_results if res is not None]
                if filtered_results:
                    for result in filtered_results:
                        synonyms = get_display_name_from_snowstorm(result)
                        name_concept_mapping[corrected_name.lower()] = result
                        for synonym in synonyms:
                            name_concept_mapping[synonym.lower()] = result
                    return ', '.join(filtered_results), "Used Llama3 to get the term"

    return (None, "")

def process_concept_id(name, concept_id, correction_status):
    results = []
    if "," in concept_id:  # Check if concept_id contains multiple IDs
        individual_ids = concept_id.split(", ")
        for individual_id in individual_ids:
            concept_name = get_fsn_name(individual_id)
            url = f"https://browser.ihtsdotools.org/?perspective=full&conceptId1={individual_id}&edition=MAIN/2024-08-01&release=&languages=en"
            icd10_code, advice = retrieve_ICD10_code_and_advice(individual_id)
            results.append({
                "term": name,
                "system ": "SNOMED CT",
                "code ": individual_id,
                "text": concept_name,
                "Retrival Method": correction_status,
                "url": url,
                "ICD10_code": icd10_code,
                "Mapping_advice": advice
            })
    else:
        concept_name = get_fsn_name(concept_id)
        url = f"https://browser.ihtsdotools.org/?perspective=full&conceptId1={concept_id}&edition=MAIN/2024-08-01&release=&languages=en"
        icd10_code, advice = retrieve_ICD10_code_and_advice(concept_id)
        results.append({
            "term": name,
            "system ": "SNOMED CT",
            "code ": concept_id,
            "text": concept_name,
            "Retrival Method": correction_status,
            "url": url,
            "ICD10_code": icd10_code,
            "Mapping_advice": advice
        })
    return results

def snomed_code_not_present(name: str) -> dict[str, list[dict[str, str]]]:
    results = []
    split_words = name.lower().split()

    if "and" in split_words or "with" in split_words or "," in split_words:
        concept_id = get_concept_id(name)
        if concept_id:
            name_concept_mapping[name.lower()] = concept_id
            concept_name = get_fsn_name(concept_id)
            synonyms = get_display_name_from_snowstorm(concept_id)
            for synonym in synonyms:
                name_concept_mapping[synonym.lower()] = concept_id
            correction_status = "Diagnosis found from SNOMED"
            results.extend(process_concept_id(name, concept_id, correction_status))

    corrected_names = [name.strip() for name in re.split(r'(?:\s*(?:\band\b|\b,\b|\bwith\b)\s*)+', name, flags=re.IGNORECASE)]

    for corrected_name in corrected_names:
        concept_id, correction_status = find_code(corrected_name)
        if concept_id and correction_status:
            results.extend(process_concept_id(corrected_name, concept_id, correction_status))
        else:
            correction_status = 'Concept ID not found'
            print(f"Concept ID not found for diagnostic name '{corrected_name}'.")
            results.append({
                "term": corrected_name,
                "system ": "SNOMED CT",
                "code ": None,
                "text": None,
                "Retrival Method": correction_status,
                "url": "N/A",
                "ICD10_code": "N/A",
                "Mapping_advice": "N/A"
            })

    return {"results": results}


class DiagnosisRequest(BaseModel):
    diagnosis_type: str
    diagnostic_term: str


@app.post("/get_snomed_code")
def get_snomed_code(request: DiagnosisRequest):
    diagnostic_term = request.diagnostic_term.strip()
    response = snomed_code_not_present(diagnostic_term)
    return response
