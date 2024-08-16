import pandas as pd
import requests
import csv
from spellchecker import SpellChecker
import re
import wordsegment
import spacy
import subprocess
import datetime

wordsegment.load()
name_concept_mapping = dict()

def segment_compound_word(compound_word):
    # Segment the compound word into individual words
    segmented_words = wordsegment.segment(compound_word)
    
    # Check if segmentation is possible
    if len(segmented_words) > 1:
        if 's' in segmented_words:
            segmented_words.remove('s')
        # If segmentation is possible, return the words with spaces in between
        return ' '.join(segmented_words)
    else:
        # If segmentation is not possible, return the original compound word
        return compound_word

#Corrects spelling of the words
def correct_text(text):
    spell = SpellChecker()
    words = text.split()
    corrected_text = []
    for word in words:
        # Correct the spelling of each word
        corrected_word = spell.correction(word)
        corrected_text.append(corrected_word)
    if None in corrected_text:
        return None
    return ' '.join(corrected_text)

# This function checks if the concept is active or not
def is_concept_active(code):
    url = f"http://localhost:8080/browser/MAIN/concepts/{code}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            # Check if the 'active' field is True
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

# Function to call medllama2 using ollama
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

            # Send all synonyms to Llama for semantic comparison
                synonyms_list = list(synonym_concept_mapping.keys())
                query = f"Which of these terms is the closest in meaning to '{name}': {', '.join(synonyms_list)}? Provide the answer in the format [closest term] or [None]."
                result = run_ollama_medllama2(query)
                
                # Parse the result to find the closest synonym or None
                match = re.search(r'\[(.*?)\]', result)
                if match:
                    closest_term = match.group(1).strip().lower()
                    if closest_term != "none":
                        return synonym_concept_mapping.get(closest_term, None)
                
                # If Llama returns 'None' or no match is found, proceed to the next step or return None
                return None
        else:
            print(f"Concept ID not found for diagnostic name '{name}'")
            return None
    except Exception as e:
        print(f"Error fetching concept ID from Snowstorm server: {e}")
        return None

#check if a name is present in the synonyms
def is_display_name_present(corrected_name,display_names):
    for name in display_names:
        if name.lower() in corrected_name.lower():
            return True
    return False

#update the data with the code found
def update_code(data,index,concept_id,i):
    if i == 0:
        data.at[index, 'concept_id_primary'] = concept_id
    elif i == 1:
        data.at[index, 'concept_id_secondary'] = concept_id
    else:
        existing_value = data.at[index, 'concept_id_secondary']
        if existing_value:
            data.at[index, 'concept_id_secondary'] = f"{existing_value}, {concept_id}"
        else:
            data.at[index, 'concept_id_secondary'] = concept_id

#If snomed code is present in the entry, it is veryfied here.Function is Not in use currently
def snomed_code_present(data,corrected_names,current_code,index,row):
    corrected_names = corrected_names = [name.strip() for name in re.split(r'(?:\s*(?:\band\b|\b,\b|\bwith\b)\s*)+', corrected_names , flags=re.IGNORECASE)]
    for i, corrected_name in enumerate(corrected_names):
        if corrected_name.lower() in name_concept_mapping and name_concept_mapping[corrected_name.lower()] == current_code:
            data.at[index, 'correction_status'] = 'No correction needed'
            update_code(data, index, current_code, i)
        else:
            display_names = get_display_name_from_snowstorm(current_code)
            if corrected_name.lower() in map(str.lower, display_names) or row['hrgstr_diagnostic_name'].strip().lower() in map(str.lower, display_names):
                data.at[index, 'correction_status'] = 'No correction needed'
                update_code(data, index, current_code, i)
                if corrected_name.lower() in map(str.lower, display_names):
                    name_concept_mapping[corrected_name.lower()] = current_code
                    for name in display_names:
                        name_concept_mapping[name.lower()] = current_code
                else:
                    name_concept_mapping[row['hrgstr_diagnostic_name'].strip().lower()] = current_code
            elif is_display_name_present(corrected_name.lower(), display_names):
                data.at[index, 'correction_status'] = 'No correction needed. But slight error is possible'
                update_code(data, index, current_code, i)
                name_concept_mapping[row['hrgstr_diagnostic_name'].strip()] = current_code
            else:
                data.at[index, 'correction_status'] = f'Data Mismatch. Code points to {display_names[0]}'
                print(f"Diagnostic name '{corrected_name}' (entry {index}) not found in display names.")
    return data

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

#Manipulating the string to get the code
def find_code(corrected_name):
        #Check if code is in dictionary
        concept_id = name_concept_mapping.get(corrected_name.lower())
        if concept_id == None:
            # First, try searching the diagnostic name as it is
            concept_id = get_concept_id(corrected_name)
        if concept_id == None:
            #join the words, removing the spaces and call snomed server
            word = re.sub(r'\s+', '', corrected_name)
            concept_id = get_concept_id(word.lower())
        if concept_id == None:
            word = segment_compound_word(corrected_name.lower())
            concept_id = get_concept_id(word.lower())
        if concept_id:
            #name_concept_mapping.setdefault(corrected_name.lower(),concept_id)
            #adding all synonyms to the dictionary
            synonyms = get_display_name_from_snowstorm(concept_id)
            name_concept_mapping[corrected_name.lower()] = concept_id
            for synonym in synonyms:
                name_concept_mapping[synonym.lower()] = concept_id 
            return (concept_id,"Diagnosis found from SNOMED")
        else:
            #Check if the words in corrected_name is a subset in any of the elements in dictionary
            for element,id in name_concept_mapping.items():
                words = element.lower().split()
                if corrected_name.lower() in words:
                    concept_id = id
                    break
            if concept_id == None:
                #checking the same by removing the spaces
                word = re.sub(r'\s+', '', corrected_name)
                concept_id = name_concept_mapping.get(word.lower())
            if concept_id:
                #name_concept_mapping.setdefault(corrected_name.lower(),concept_id)
                #print(f"Added concept_id from dictionary (entry {index}) ")    
                return (concept_id,"Diagnosis Found in dictionary")
            else:
                # Check if any of the words in the diagnostic name are present in the name_concept_mapping dictionary
                for word in corrected_name.split():
                    concept_id = name_concept_mapping.get(word.lower())
                    if concept_id:
                        break  # Break the loop if a match is found
                if concept_id:
                        return (concept_id,'Partial diagnosis name present in dictionary')
                        #print(f"Added concept_id from dictionary (entry {index})")
                else:
                    query = (
                        f"Only provide me the primary disease or condition terms/expand medical abbreviations without any conjunctions or descriptive qualifiers. "
                        f"If no corrections are needed, return the input as a single term. "
                        f"Provide the corrected term in the format ['corrected_term']. "
                        f"Diagnosis: '{corrected_name}'"
                    )
                    medllama_output = run_ollama_medllama2(query)
    
                    if medllama_output:
                        corrected_terms = extract_terms_from_medllama_output(medllama_output)
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

#Splits the word if required and calls fucntions to get the snomed code
def snomed_code_not_present(data,corrected_names,index,row):
    split_words = corrected_names.lower().split()
    if "and" in split_words or "with" in split_words or "," in split_words:
        #If the name has connceting words, seach for it as a whole once if present in snomed
        concept_id = get_concept_id(corrected_names)
        if concept_id:
            update_code(data, index, concept_id, 0)
            #name_concept_mapping.setdefault(corrected_names.lower(),concept_id)
            data.at[index, 'correction_status'] = 'Diagnosis found from SNOMED'
            name_concept_mapping[corrected_names.lower()] = concept_id
            synonyms = get_display_name_from_snowstorm(concept_id)
            for synonym in synonyms:
                name_concept_mapping[synonym.lower()] = concept_id
            return data
    #If not, Split the word with "and" "with" "," to get individual diagnosis names
    corrected_names = [name.strip() for name in re.split(r'(?:\s*(?:\band\b|\b,\b|\bwith\b)\s*)+', corrected_names , flags=re.IGNORECASE)]
    for i, corrected_name in enumerate(corrected_names):
        #call the find_code function to find the code
        concept_id,correction_status = find_code(corrected_name)
        if concept_id and correction_status != "":
            #If code found, update code
            update_code(data,index,concept_id,i)
            data.at[index, 'correction_status'] = correction_status
        else:
            # If code was not found, mark as no ID found
            if i == 0:
                data.at[index, 'correction_status'] = 'Primary Concept ID not found'
            elif i == 1:
                print(corrected_name)
                data.at[index, 'correction_status'] = 'Secondary Concept ID not found'
            else:
                # For the third corrected name onwards, append to the existing value with a comma
                existing_value = data.at[index, 'concept_id_secondary']
                if existing_value:
                    data.at[index, 'concept_id_secondary'] = f"{existing_value}, {concept_id}"
                else:
                    data.at[index, 'concept_id_secondary'] = concept_id
                    data.at[index, 'correction_status'] = 'Secondary Concept ID not found'
                    print(f"Concept ID not found for diagnostic name '{corrected_name}' (entry {index}).")
        # Get the current timestamp as a datetime object
        current_time = datetime.datetime.now()

        # Format the timestamp as a string
        formatted_timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S.%f")

        # Print the formatted timestamp
        print(formatted_timestamp)
        
    return data

def process_chunk(chunk):
    chunk['correction_status'] = ''
    chunk['concept_id_primary'] = ''
    chunk['concept_id_secondary'] = ''
    chunk['Snomed Match?'] = ''
    chunk['reason for mismatch'] = ''
    
    for index, row in chunk.iterrows():
        # get the diagnosis name and code if present in the row
        current_code = row['hrgnum_diagnostic_code']
        corrected_names = row['hrgstr_diagnostic_name'].strip()
        # clean the name
        corrected_names = re.sub(r'^[^a-zA-Z0-9,]+', '', corrected_names)
        chunk = snomed_code_not_present(chunk, corrected_names, index, row)

        # Re-fetch the row to ensure we have the updated data
        row = chunk.loc[index]

        print(f"Index: {index}, Current Code: {current_code}, Concept ID Primary: {row['concept_id_primary']}")

        if str(current_code).isdigit() and str(current_code) != '0':
            # If code is present in the row, this compares that code with the code found by us.
            if row['hrgnum_diagnostic_code'] == row['concept_id_primary']:
                chunk.at[index, 'Snomed Match?'] = "YES"
            else:
                chunk.at[index, 'Snomed Match?'] = "NO"
                # Check if the mismatch is because of the given code being an inactive one?
                if not is_concept_active(row['hrgnum_diagnostic_code']):
                    chunk.at[index, 'reason for mismatch'] = "Punjab Data code points to an Inactive concept"
                # if not, check if it is because the code type of the given concept is not a finding or disorder.
                elif not check_fsn_type(row['hrgnum_diagnostic_code']):
                    display_names = get_display_name_from_snowstorm(row['hrgnum_diagnostic_code'])
                    for name in display_names:
                        match = re.search(r'\(([^)]+)\)', name)
                        if match:
                            type_ = match.group(1)
                            break
                    chunk.at[index, 'reason for mismatch'] = f"Punjab Data Code points to a {type_} concept"
                else:
                    # If not both of them, it can be our matching error or else a totally wrong code given in the data
                    chunk.at[index, 'reason for mismatch'] = "Some other reason for mismatch"
    return chunk

# Reading the CSV and adding columns
def reading_csv(filename):
    # Define the number of rows to process
    num_rows_to_process = 100
    chunk_size = num_rows_to_process
    chunks = pd.read_csv(filename, chunksize=chunk_size)

    # Initialize an empty DataFrame to collect processed chunks
    processed_data = pd.DataFrame()

    processed_rows = 0

    for chunk in chunks:
        if processed_rows >= num_rows_to_process:
            break

        chunk = process_chunk(chunk)
        processed_data = pd.concat([processed_data, chunk], ignore_index=True)

        processed_rows += len(chunk)
        if processed_rows >= num_rows_to_process:
            processed_data = processed_data.head(num_rows_to_process)
            break

    modified_data = processed_data[processed_data['correction_status'] != '']
    modified_filename = 'modified_with_llama_method_' + str(num_rows_to_process) + '_' + filename
    # adding the new columns to the csv
    selected_columns = ['hrgnum_diagnostic_code', 'gdt_entry_date', 'hrgstr_diagnostic_name', 'correction_status', 'concept_id_primary', 'concept_id_secondary', 'Snomed Match?', 'reason for mismatch']
    modified_data[selected_columns].to_csv(modified_filename, index=False)
    print("Modified CSV file saved successfully:", modified_filename)

    mapping_filename = 'mapping_dictionary.csv'
    with open(mapping_filename, 'w', newline="") as file:
        writer = csv.writer(file)
        writer.writerow(['corrected_name', 'snomed_concept_id'])
        for name, concept_id in name_concept_mapping.items():
            writer.writerow([name, concept_id])

    print("Mapping dictionary saved successfully:", mapping_filename)

# Specify the filename
filename = 'diagnosis_data.csv'

# Call the function to read the csv
reading_csv(filename)
