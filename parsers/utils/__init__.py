import requests
import xml.etree.ElementTree as ET


def clean_title(title):
    title = title.split("Running Title")[0]
    title = title.replace("^Running Title: ", "")
    title = title.replace("^Short Title: ", "")
    title = title.replace("^Title: ", "")
    title = title.strip()
    return title


def find_references(doi):
    """ Returns the references of a document as a <class 'list'> of <class 'dict'>.
    This is a list of documents cited by the current document.
    """
    if doi is None:
        return None

    references = []
    if doi:
        response = requests.get(f"https://opencitations.net/index/api/v1/references/{doi}").json()
        if response:
            references = [{"doi": r['cited'].replace("coci =>", ""), "text": r['cited'].replace("coci =>", "")} for r in response]

    if references:
        return references
    else:
        return None


def find_cited_by(doi):
    """ Returns the citations of a document as a <class 'list'> of <class 'str'>.
    A list of DOIs of documents that cite this document.
    """
    if doi is None:
        return None

    citations = []
    if doi:
        response = requests.get(f"https://opencitations.net/index/api/v1/citations/{doi}").json()
        if response:
            citations = [{"doi": r['citing'].replace("coci =>", ""), "text": r['citing'].replace("coci =>", "")} for r in response]
    if citations:
        return citations
    else:
        return None
    
    
def find_pmcid_and_pubmed_id(doi):
    """ Returns dictionary containing pmcid and pubmed_id if available.
    Format:
        {
            pmcid : 'pmcid_string',
            pubmed_id : 'pubmed_id__string'
        }
    Returns None for either id if not available. Returns None for both ids if doi
    is None or request fails.
    """
    session = requests.Session()
    try:
        doi2otherid_url = 'https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=%s' % doi
        response = session.get(doi2otherid_url)
        root = ET.fromstring(response.content)
        ids = dict()
    except:
        return {'pmcid' : None, 'pubmed_id' : None}
    if 'pmcid' in root.find('record').attrib:
        ids['pmcid'] = root.find('record').attrib['pmcid']
    else:
        ids['pmcid'] = None
    if 'pmid' in root.find('record').attrib:
        ids['pubmed_id'] = root.find('record').attrib['pmid']
    else:
        ids['pubmed_id'] = None
    return ids
