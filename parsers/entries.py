from base import Parser, VespaDocument, indexes
from mongoengine.queryset.visitor import Q
import json
import re
from datetime import datetime
import requests
from utils import clean_title, find_cited_by, find_references
from elsevier import ElsevierDocument
from google_form_submissions import GoogleFormSubmissionDocument
from litcovid import LitCovidCrossrefDocument, LitCovidPubmedDocument
from biorxiv import BiorxivDocument
from cord19 import CORD19Document
from pho import PHODocument
from mongoengine import ListField, GenericReferenceField, DoesNotExist

class EntriesDocument(VespaDocument):
    meta = {"collection": "entries_vespa",
            "indexes": indexes
    }    

    source_documents = ListField(GenericReferenceField(), required=True)

    @staticmethod
    def find_matching_doc(doc):
        #This could definitely be better but I can't figure out how to mangle mongoengine search syntax in the right way
        doi = doc['doi']
        pubmed_id = doc['pubmed_id']
        pmcid = doc['pmcid']
        scopus_eid = doc['scopus_eid']
        if doi:
            try:
                matching_doc = EntriesDocument.objects(Q(doi__iexact=doi)).get()
                return matching_doc
            except DoesNotExist:
                pass
        if pubmed_id:
            try:
                matching_doc = EntriesDocument.objects(Q(pubmed_id__iexact=pubmed_id)).get()
                return matching_doc
            except DoesNotExist:
                pass
        if pmcid:
            try:
                matching_doc = EntriesDocument.objects(Q(pmcid__iexact=pmcid)).get()
                return matching_doc
            except DoesNotExist:
                pass

        if scopus_eid:
            try:
                matching_doc = EntriesDocument.objects(Q(scopus_eid__iexact=scopus_eid)).get()
                return matching_doc
            except DoesNotExist:
                pass

        return None

entries_keys = EntriesDocument._fields.keys()

# -*- coding: utf-8 -*-
"""
Created on Fri Apr  3 13:36:44 2020

@author: elise
"""


def add_pre_proof_and_clean(entry):
    if entry['title'] != None and 'Journal Pre-proof' in entry['title']:
        entry['is_pre_proof'] = True
        entry['title'] = remove_pre_proof(entry['title'])

    else:
        entry['is_pre_proof'] = False
    return entry


def remove_pre_proof(title):
    clean_title = title.replace('Journal Pre-proofs', ' ')
    clean_title = clean_title.replace('Journal Pre-proof', ' ')
    clean_title = clean_title.strip()
    if len(clean_title) == 0:
        clean_title = None
    return clean_title


def remove_html(abstract):
    # necessary to check this to avoid removing text between less than and greater than signs
    if abstract is not None and bool(re.search('<.*?>.*?</.*?>', abstract)):
        clean_abstract = re.sub('<.*?>', '', abstract)
        return clean_abstract
    else:
        return abstract


def clean_data(doc):
    cleaned_doc = doc
    cleaned_doc = add_pre_proof_and_clean(cleaned_doc)
    cleaned_doc['abstract'] = remove_html(cleaned_doc['abstract'])
    if cleaned_doc['journal'] == 'PLoS ONE':
        cleaned_doc['journal'] = 'PLOS ONE'

    return cleaned_doc



def merge_documents(high_priority_doc, low_priority_doc):
    # Merge documents from two different source collections
    # Where they disagree, take the version from high_priority_doc

    merged_doc = dict()

    for k in entries_keys:
        # Treat human annotations separately - always merge them into a list
        if k not in ['summary_human', 'keywords', 'keywords_ML', 'category_human', 'category_human']:

            # First fill in what we can from high_priority_doc
            if k in high_priority_doc.keys() and high_priority_doc[k] is not None and high_priority_doc[k] not in ["",
                                                                                                                   []]:
                merged_doc[k] = high_priority_doc[k]
            elif k in low_priority_doc.keys() and low_priority_doc[k] is not None and low_priority_doc[k] not in ["",
                                                                                                                  []]:
                merged_doc[k] = low_priority_doc[k]
            else:
                merged_doc[k] = None

        else:
            # Now merge the annotation categories into lists
            merged_category = []
            for doc in [high_priority_doc, low_priority_doc]:
                if k in doc.keys():
                    if isinstance(doc[k], str):
                        if not doc[k] in merged_category:
                            merged_category.append(doc[k])
                    elif isinstance(doc[k], list):
                        for e in doc[k]:
                            if not e in merged_category:
                                merged_category.append(e)

            merged_doc[k] = list(set([anno.strip() for anno in merged_category]))

    merged_doc['last_updated'] = datetime.now()

    for date_bool_key in ['has_day', 'has_month', 'has_year']:
        if date_bool_key not in merged_doc.keys():
            merged_doc[date_bool_key] = False

    # Common starting text to abstracts that we want to clean
    preambles = ["Abstract Background", "Abstract:", "Abstract", "Graphical Abstract Highlights d", "Resumen", "Résumé"]
    elsevier_preamble = "publicly funded repositories, such as the WHO COVID database with rights for unrestricted research re-use and analyses in any form or by any means with acknowledgement of the original source. These permissions are granted for free by Elsevier for as long as the COVID-19 resource centre remains active."
    preambles.append(elsevier_preamble)

    if 'abstract' in merged_doc.keys() and merged_doc['abstract'] is not None:
        if isinstance(merged_doc['abstract'], list):
            merged_doc['abstract'] = " ".join(merged_doc['abstract'])

        if 'a b s t r a c t' in merged_doc['abstract']:
            merged_doc['abstract'] = merged_doc['abstract'].split('a b s t r a c t')[1]

        try:
            merged_doc['abstract'] = re.sub('^<jats:title>*<\/jats:title>', '', merged_doc['abstract'])
            merged_doc['abstract'] = re.sub('<\/?jats:[^>]*>', '', merged_doc['abstract'])
        except TypeError:
            pass
        for preamble in preambles:
            try:
                merged_doc['abstract'] = re.sub('^{}'.format(preamble), '', merged_doc['abstract'])
            except TypeError:
                pass

    if 'title' in merged_doc.keys() and merged_doc['title'] is not None:
        if isinstance(merged_doc['title'], list):
            merged_doc['title'] = " ".join(merged_doc['title'])

    if 'journal' in merged_doc.keys() and merged_doc['journal'] is not None:
        if isinstance(merged_doc['journal'], list):
            merged_doc['journal'] = " ".join(merged_doc['journal'])

    merged_doc = clean_data(merged_doc)
    if merged_doc['abstract'] is not None:
        merged_doc['abstract'] = merged_doc['abstract'].strip()
    return merged_doc

parsed_collections = [
    GoogleFormSubmissionDocument,
    PHODocument,
    LitCovidCrossrefDocument,
    LitCovidPubmedDocument,
    BiorxivDocument,
    ElsevierDocument,
    CORD19Document,
]

def build_entries():
    for collection in parsed_collections:
        print(collection)
        for doc in collection.objects:
            id_fields = [doc['doi'], 
            doc['pubmed_id'],
            doc['pmcid'],
            doc['scopus_eid'],
            ]
            matching_doc = EntriesDocument.find_matching_doc(doc)
            if matching_doc:
                insert_doc = EntriesDocument(**merge_documents(matching_doc, doc))
            elif any([x is not None for x in id_fields]):
                insert_doc = EntriesDocument(**{k:v for k,v in doc.to_mongo().items() if k in entries_keys})
            else:
                insert_doc = None
            if insert_doc:
                insert_doc.source_documents = insert_doc.source_documents.append(doc)
                insert_doc.save()
