import threading

import requests
import json
import urllib
import glob
from pprint import pprint
import re
from datetime import datetime
import difflib
import Levenshtein
import collections
import numpy as np
from statsmodels.stats.weightstats import DescrStatsW
import seaborn as sns
import multiprocessing as mp
import pandas as pd

from common_utils import get_mongo_db

# TODO: need a num from stas here

PAPER_COLLECTIONS = {
    'CORD_biorxiv_medrxiv',
    'CORD_comm_use_subset',
    'CORD_custom_license',
    'CORD_noncomm_use_subset',
}
# title len stat shows that
# mean = 98.1516258677384
# std = 37.430021136179725
# percentile:
# 0.00      0
# 0.01     16
# 0.02     25
# 0.03     31
# 0.04     36
# 0.05     39
# 0.10     51
# 0.25     72
# 0.50     97
# 0.75    121
# 0.95    163
# 0.97    174
# 0.99    194
LEAST_TITLE_LEN = 16
AVG_TITLE_LEN = 97
LEAST_TITLE_SIMILARITY = 0.95
IGNORE_BEGIN_END_SIMILARITY = 0.90
# abstract len stat shows that
# mean = 1544.1819507148232
# std = 1116.3547477100615
# percentile:
# 0.00       1
# 0.01     132
# 0.02     234
# 0.03     316
# 0.04     360
# 0.05     414
# 0.10     676
# 0.25    1020
# 0.50    1394
# 0.75    1800
# 0.95    2927
# 0.97    3614
# 0.99    5909
LEAST_ABS_LEN = 132
LEAST_ABS_SIMILARITY = 0.90

#######################################
# functions for stats
#######################################

def doi_existence_stat(mongo_db):
    for col_name in mongo_db.collection_names():
        if col_name not in PAPER_COLLECTIONS:
            continue
        col = mongo_db[col_name]
        query_w_doi = col.find({'doi': {'$exists': True}})
        query_w_doi_len_gt_0 = col.find({
            'doi': {'$exists': True},
            '$where': 'this.doi.length > 0',
        })
        query_w_crossref_tried = col.find({'tried_crossref_doi': True})
        query_w_csv_tried = col.find({'tried_csv_doi': True})
        query_wo_doi_title_empty = col.find({
            'doi': {'$exists': False},
            'metadata': {'$exists': True},
            '$where': 'this.metadata.title.length == 0',
        })
        print('col_name', col_name)
        print('col.count()', col.count())
        print('query_w_doi', query_w_doi.count())
        print('query_w_doi_len_gt_0', query_w_doi_len_gt_0.count())
        print('query_w_crossref_tried', query_w_crossref_tried.count())
        print('query_w_csv_tried', query_w_csv_tried.count())
        print('query_wo_doi_title_empty', query_wo_doi_title_empty.count())
        print()


def title_len_stat(mongo_db):
    len_counter_db = collections.Counter()
    len_counter_cr = collections.Counter()
    for col_name in mongo_db.collection_names():
        if col_name not in PAPER_COLLECTIONS:
            continue
        col = mongo_db[col_name]
        query_w_doi = col.find({'doi': {'$exists': True}})
        for doc in query_w_doi:
            if ('metadata' in doc
                    and 'title' in doc['metadata']
                    and isinstance(doc['metadata']['title'], str)
            ):
                len_counter_db[len(doc['metadata']['title'])] += 1
            if ('crossref_raw_result' in doc
                    and 'title' in doc['crossref_raw_result']
                    and isinstance(doc['crossref_raw_result']['title'], list)
                    and len(doc['crossref_raw_result']['title']) == 1
            ):
                len_counter_cr[len(doc['crossref_raw_result']['title'][0])] += 1

    # stat for db titles
    sorted_len = sorted(len_counter_db.keys())
    weights = [len_counter_db[l] for l in sorted_len]
    weighted_stats = DescrStatsW(sorted_len, weights=weights)
    sns.barplot(sorted_len, weights)
    percentile = weighted_stats.quantile(
        probs=[0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.1, 0.25, 0.5, 0.75, 0.95, 0.97, 0.99]
    )
    print('len_counter_db')
    pprint(len_counter_db)
    print('weighted_stats.mean', weighted_stats.mean)
    print('weighted_stats.std', weighted_stats.std)
    print('percentile')
    print(percentile)

    # stat for cr titles
    sorted_len = sorted(len_counter_cr.keys())
    weights = [len_counter_cr[l] for l in sorted_len]
    weighted_stats = DescrStatsW(sorted_len, weights=weights)
    #     sns.barplot(sorted_len, weights)
    percentile = weighted_stats.quantile(
        probs=[0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.1, 0.25, 0.5, 0.75, 0.95, 0.97, 0.99]
    )
    print('len_counter_cr')
    pprint(len_counter_cr)
    print('weighted_stats.mean', weighted_stats.mean)
    print('weighted_stats.std', weighted_stats.std)
    print('percentile')
    print(percentile)

    return len_counter_db, len_counter_cr


def abs_len_stat(mongo_db):
    len_counter = collections.Counter()
    for col_name in mongo_db.collection_names():
        if col_name not in PAPER_COLLECTIONS:
            continue
        col = mongo_db[col_name]
        query_w_doi = col.find({'abstract': {'$exists': True}})
        for doc in query_w_doi:
            # get abstract
            abstract = None
            if 'abstract' in doc and len(doc['abstract']) > 0:
                abstract = ''
                for fragment in doc['abstract']:
                    if ('text' in fragment
                            and isinstance(fragment['text'], str)
                            and len(fragment['text']) > 0
                    ):
                        abstract += fragment['text'].strip() + ' '

                abstract = abstract.strip()
                if len(abstract) == 0:
                    abstract = None

            if abstract is not None:
                #                 print(abstract)
                len_counter[len(abstract)] += 1

    # stat for db abs
    sorted_len = sorted(len_counter.keys())
    weights = [len_counter[l] for l in sorted_len]
    weighted_stats = DescrStatsW(sorted_len, weights=weights)
    sns.barplot(sorted_len, weights)
    percentile = weighted_stats.quantile(
        probs=[0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.1, 0.25, 0.5, 0.75, 0.95, 0.97, 0.99]
    )
    print('len_counter')
    pprint(len_counter)
    print('weighted_stats.mean', weighted_stats.mean)
    print('weighted_stats.std', weighted_stats.std)
    print('percentile')
    print(percentile)

    return len_counter

#######################################
# functions for doi searching task
#######################################

def clean_title(title):
    clean_title = title.split("Running Title")[0]
    clean_title = re.sub('( [0-9])*$', '', clean_title)
    clean_title = clean_title.replace("Running Title: ", "")
    clean_title = clean_title.replace("Short Title: ", "")
    clean_title = clean_title.replace("Title: ", "")
    clean_title = clean_title.lower()
    clean_title = clean_title.strip()
    return clean_title

def correct_pd_dict(input_dict):
    """
        Correct the encoding of python dictionaries so they can be encoded to mongodb
        https://stackoverflow.com/questions/30098263/inserting-a-document-with-
        pymongo-invaliddocument-cannot-encode-object
        inputs
        -------
        input_dict : dictionary instance to add as document
        output
        -------
        output_dict : new dictionary with (hopefully) corrected encodings
    """

    output_dict = {}
    for key1, val1 in input_dict.items():
        # Nested dictionaries
        if isinstance(val1, dict):
            val1 = correct_pd_dict(val1)

        if isinstance(val1, np.bool_):
            val1 = bool(val1)

        if isinstance(val1, np.int64):
            val1 = int(val1)

        if isinstance(val1, np.float64):
            val1 = float(val1)

        if isinstance(val1, set):
            val1 = list(val1)

        output_dict[key1] = val1

    return output_dict

def text_similarity_by_char(text_1,
                            text_2,
                            quick_mode=False,
                            enable_ignore_begin_end=False,
                            least_text_len=LEAST_TITLE_LEN,
                            ignore_begin_end_thresh=IGNORE_BEGIN_END_SIMILARITY):
    """
    calculate similarity by comparing char difference

    :param text_1:
    :param text_2:
    :return:
    """

    ref_len_ = max(float(len(text_1)), float(len(text_2)), 1.0)
    max(float(len(text_2)), 1.0)
    # find the same strings
    if not quick_mode:
        same_char = difflib.SequenceMatcher(None, text_1, text_2).get_matching_blocks()
        same_char = list(filter(lambda x: x.size > 0, same_char))
        same_char_1 = sum(
            [tmp_block.size for tmp_block in same_char]
        ) / float(max(len(text_1), len(text_2), 1.0))
        same_char_2 = 0
        if enable_ignore_begin_end and len(same_char) > 0:
            text_1 = text_1[same_char[0].a: same_char[-1].a + same_char[-1].size]
            text_2 = text_2[same_char[0].b: same_char[-1].b + same_char[-1].size]
            if (len(text_1) > least_text_len
                and len(text_2) > least_text_len
                and len(text_1)/max(len(text_1), 1.0) > ignore_begin_end_thresh
                and len(text_2)/max(len(text_2), 1.0) > ignore_begin_end_thresh
            ):
                same_char_2 = sum(
                    [tmp_block.size for tmp_block in same_char]
                ) / float(max(len(text_1), len(text_2), 1.0))
        same_char_ratio = max(same_char_1, same_char_2)
    # find the different strings
    diff_char_ratio = 1 - Levenshtein.distance(text_1, text_2) / float(
        max(min(len(text_1), len(text_2)), 1.0))

    if not quick_mode:
        similarity = (same_char_ratio + diff_char_ratio) / 2.0
    else:
        similarity = diff_char_ratio
    # print(text_1, text_2, same_char, diff_char, similarity, maxlarity, answer_simis)
    return similarity

def doi_match_a_batch_by_crossref(task_batch):
    mongo_db = get_mongo_db('../config.json')
    for i, task in enumerate(task_batch):
        if i % 100 == 0:
            print('thread', threading.currentThread().getName())
            print('processing the {}th out of {}'.format(i, len(task_batch)))
        col = mongo_db[task['col_name']]

        # get doc
        doc = col.find_one({'_id': task['_id']})
        if doc is None:
            continue

        doc_updated = False

        # get metadata
        metadata = None
        if ('metadata' in doc):
            metadata = doc['metadata']
        else:
            # let's supporse metadata is always used first
            # TODO: we can also use abstract when metadata is not available
            continue


        # get title
        title = None
        raw_title = None
        if metadata is not None:
            if not ('title' in metadata
                and isinstance(metadata['title'], str)
                and len(metadata['title'].strip()) > 0
            ):
                # doc w/o is minor part let's ignore them first
                # TODO: we can also use abstract when metadata is not available
                continue
            raw_title = metadata['title']
            print('raw_title', raw_title)
            title = clean_title(raw_title)


        # get author
        author_names = None
        if metadata is not None:
            try:
                author_names = ",".join([a['last'] for a in metadata['authors']])
            except KeyError:
                author_names = None

        # query cross_ref
        query_url = 'https://api.crossref.org/works'
        query_params = {
            'sort': 'relevance',
            'order': 'desc',
        }
        if title:
            # after some experiments, we use pass the query value in plain str rather than html str
            # therefore, use title instead of urllib.parse.quote_plus(title)
            query_params['query.bibliographic'] = title
        # TODO: might need to double check if exact title matching be perfect (author might be different?)
        # TODO: might be wrong here need to clean db when only author info is used to retrieve data
        elif author_names:
            query_params['query.bibliographic'] = author_names
        # TODO: might also use email to search?

        try:
            cross_ref_results = requests.get(
                query_url,
                params=query_params,
            )
        except:
            print('request to cross_ref failed!')
            continue
        try:
            cross_ref_results = cross_ref_results.json()
        except Exception as e:
            print('query result cannot be jsonified!')
            print('cross_ref_results.text', cross_ref_results.text)
            print('cross_ref_results.status_code', cross_ref_results.status_code)
            print('cross_ref_results.reason', cross_ref_results.reason)
            print()
            continue

        # filter out empty query results
        if not ('message' in cross_ref_results
            and 'items' in cross_ref_results['message']
            and isinstance(cross_ref_results['message']['items'], list)
            and len(cross_ref_results['message']['items']) > 0
        ):
            print('EMPTY RESULT')
            pprint(cross_ref_results)
            print()
            continue
        else:
            cross_ref_results = cross_ref_results['message']['items']

        # filter out query results without title
        # TODO: maybe abtract is available
        #  use item['abstract']
        cross_ref_results = list(filter(
            lambda x: (
                    'title' in x
                    and isinstance(x['title'], list)
                    and len(x['title']) > 0
            ),
            cross_ref_results
        ))
        # exit()

        # print('title', title)
        # print("metadata['title']", metadata['title'])
        # print('author_names', author_names)
        # pprint(r.json())
        # exit()

        # match by title directly
        matched_item = None
        if matched_item is None:
            for item in cross_ref_results:
                if len(item['title']) != 1:
                    print("len(item['title'])", len(item['title']))
                cr_title = clean_title(item['title'][0])
                similarity = text_similarity_by_char(cr_title, title)
                if (len(cr_title) > LEAST_TITLE_LEN
                    and len(title) > LEAST_TITLE_LEN
                    and similarity > LEAST_TITLE_SIMILARITY):
                    print('raw_title: ', raw_title)
                    print('title', title)
                    print("cr_title", cr_title)
                    print('similarity', similarity)
                    matched_item = item
                    break

                # if cr_title == title:
                #     matched_item = item
                #     break

        # # match by revised title
        # if matched_item is None:
        #     title = re.sub(' [0-9] ', ' ', title)
        #     for item in cross_ref_results:
        #         cr_title = item['title'][0]
        #         if cr_title == title:
        #             matched_item = item
        #             break


        # update doi found
        if matched_item is not None:
            print("FOUND")
            print()
            col.find_one_and_update(
                {"_id": doc['_id']},
                {
                    "$set": {
                        "doi": matched_item['DOI'],
                        'tried_crossref_doi': True,
                        'crossref_raw_result': matched_item,
                        'last_updated': datetime.now(),
                    }
                }
            )
            doc_updated = True
        # else:
        #     print('query_params', query_params)
        #     print('\n'.join([x['title'][0] for x in cross_ref_results]))

        # mark tried even if doi is not found but searching is completed
        if not doc_updated:
            col.find_one_and_update(
                {"_id": doc['_id']},
                {
                    "$set": {
                        "tried_crossref_doi": True,
                        'last_updated': datetime.now(),
                    }
                }
            )

def doi_match_a_batch_by_csv(task_batch):
    mongo_db = get_mongo_db('../config.json')
    csv_data = pd.read_csv('../rsc/metadata.csv')
    csv_data = csv_data.fillna('')
    csv_data['title'] = csv_data['title'].str.lower()
    for i, task in enumerate(task_batch):
        if i % 100 == 0:
            print('thread', threading.currentThread().getName())
            print('processing the {}th out of {}'.format(i, len(task_batch)))
        col = mongo_db[task['col_name']]

        # get doc
        doc = col.find_one({'_id': task['_id']})
        if doc is None:
            continue

        doc_updated = False

        # get metadata
        metadata = None
        if ('metadata' in doc):
            metadata = doc['metadata']
        else:
            # let's supporse metadata is always used first
            # TODO: we can also use abstract when metadata is not available
            continue


        # get title
        title = None
        raw_title = None
        if metadata is not None:
            if not ('title' in metadata
                and isinstance(metadata['title'], str)
                and len(metadata['title'].strip()) > 0
            ):
                # doc w/o is minor part let's ignore them first
                # TODO: we can also use abstract when metadata is not available
                continue
            raw_title = metadata['title']
            print('raw_title', raw_title)
            title = clean_title(raw_title)


        # get author
        author_names = None
        if metadata is not None:
            try:
                author_names = ",".join([a['last'] for a in metadata['authors']])
            except KeyError:
                author_names = None

        # get abstract
        abstract = None
        if 'abstract' in doc and len(doc['abstract']) > 0:
            abstract = ''
            for fragment in doc['abstract']:
                if ('text' in fragment
                    and isinstance(fragment['text'], str)
                    and len(fragment['text']) > 0
                ):
                    abstract += fragment['text'].strip() + ' '

            abstract = abstract.strip()
            if len(abstract) == 0:
                abstract = None

        # query csv_data
        matched_item = None

        # match by title
        if title is not None:
            similarity = csv_data.apply(
                lambda x: text_similarity_by_char(x['title'], title, quick_mode=True),
                axis=1
            )
            sim_csv_data = csv_data[similarity>=2*LEAST_TITLE_SIMILARITY-1]
            if len(sim_csv_data) > 0:
                similarity = sim_csv_data.apply(
                    lambda x: text_similarity_by_char(x['title'], title, quick_mode=False),
                    axis=1
                )
                sorted_similarity = similarity.sort_values(ascending=False)
                sorted_data = sim_csv_data.reindex(index=sorted_similarity.index)
                if (len(title) > LEAST_TITLE_LEN
                    and len(sorted_data.iloc[0]['title']) > LEAST_TITLE_LEN
                    and sorted_similarity.iloc[0] > LEAST_TITLE_SIMILARITY):
                    print('raw_title: ', raw_title)
                    print('title', title)
                    print("csv_title", sorted_data.iloc[0]['title'])
                    print('similarity', sorted_similarity.iloc[0])
                    print()
                    matched_item = correct_pd_dict(sorted_data.iloc[0].to_dict())

            if matched_item is None and len(sim_csv_data) > 0:
                similarity = sim_csv_data.apply(
                    lambda x: text_similarity_by_char(
                        x['title'],
                        title,
                        quick_mode=False,
                        enable_ignore_begin_end=True
                    ),
                    axis=1
                )
                sorted_similarity = similarity.sort_values(ascending=False)
                sorted_data = sim_csv_data.reindex(index=sorted_similarity.index)
                if (len(title) > LEAST_TITLE_LEN
                        and len(sorted_data.iloc[0]['title']) > LEAST_TITLE_LEN
                        and sorted_similarity.iloc[0] > LEAST_TITLE_SIMILARITY):
                    print('result after ignore_begin_end')
                    print('raw_title: ', raw_title)
                    print('title', title)
                    print("csv_title", sorted_data.iloc[0]['title'])
                    print('similarity', sorted_similarity.iloc[0])
                    print()
                    matched_item = correct_pd_dict(sorted_data.iloc[0].to_dict())

        if abstract is not None and matched_item is None:
            # match by abstract
            similarity = csv_data.apply(
                lambda x: text_similarity_by_char(x['abstract'], abstract, quick_mode=True),
                axis=1
            )
            sim_csv_data = csv_data[similarity>=2*LEAST_ABS_SIMILARITY-1]
            if len(sim_csv_data) > 0:
                similarity = sim_csv_data.apply(
                    lambda x: text_similarity_by_char(x['abstract'], abstract, quick_mode=False),
                    axis=1
                )
                sorted_similarity = similarity.sort_values(ascending=False)
                sorted_data = sim_csv_data.reindex(index=sorted_similarity.index)
                if (len(abstract) > LEAST_ABS_LEN
                    and len(sorted_data.iloc[0]['abstract']) > LEAST_TITLE_LEN
                    and sorted_similarity.iloc[0] > LEAST_ABS_SIMILARITY):
                    print('abstract', abstract)
                    print("csv_abstract", sorted_data.iloc[0]['abstract'])
                    print('similarity', sorted_similarity.iloc[0])
                    print()
                    matched_item = correct_pd_dict(sorted_data.iloc[0].to_dict())

        # update db
        set_params = {
            "tried_csv_doi": True,
            'last_updated': datetime.now(),
        }

        # update doi found
        if matched_item is not None:
            print("FOUND")
            print()
            set_params['csv_raw_result'] = matched_item
            if matched_item.get('doi') and (isinstance(matched_item['doi'], str)):
                set_params['doi'] = matched_item['doi']

            doc_updated = True

        try:
            col.find_one_and_update(
                {"_id": doc['_id']},
                {
                    "$set": set_params,
                }
            )
        except Exception as e:
            print('matched_item')
            pprint(matched_item)
            print(e)
            raise e

def foo(mongo_db, num_cores=4):
    for col_name in mongo_db.collection_names():
        # if col_name != 'CORD_noncomm_use_subset':
        #     continue
        if col_name not in PAPER_COLLECTIONS:
            continue
        col = mongo_db[col_name]
        query = col.find(
            {
                "tried_crossref_doi" : { "$exists" : True },
                "doi" : { "$exists" : False }
            },
            {
                '_id': True
            }
        )
        all_tasks = list(query)
        for task in all_tasks:
            task['col_name'] = col_name
        print('len(all_tasks)', len(all_tasks))

        parallel_arguments = []
        num_task_per_batch = int(len(all_tasks) / num_cores)
        print('num_task_per_batch', num_task_per_batch)
        for i in range(num_cores):
            if i < num_cores - 1:
                parallel_arguments.append((all_tasks[i * num_task_per_batch: (i + 1) * num_task_per_batch],))
            else:
                parallel_arguments.append((all_tasks[i * num_task_per_batch:], ))

        p = mp.Pool(processes=num_cores)
        all_summary = p.starmap(doi_match_a_batch_by_crossref, parallel_arguments)
        p.close()
        p.join()


def bar(mongo_db, num_cores=1):
    for col_name in mongo_db.collection_names():
        # if col_name != 'CORD_noncomm_use_subset':
        #     continue
        if col_name not in PAPER_COLLECTIONS:
            continue
        col = mongo_db[col_name]
        query = col.find(
            {
                "tried_csv_doi" : { "$exists" : True },
                "doi" : { "$exists" : False }
            },
            {
                '_id': True
            }
        )
        all_tasks = list(query)
        for task in all_tasks:
            task['col_name'] = col_name
        print('len(all_tasks)', len(all_tasks))

        parallel_arguments = []
        num_task_per_batch = int(len(all_tasks) / num_cores)
        print('num_task_per_batch', num_task_per_batch)
        for i in range(num_cores):
            if i < num_cores - 1:
                parallel_arguments.append((all_tasks[i * num_task_per_batch: (i + 1) * num_task_per_batch],))
            else:
                parallel_arguments.append((all_tasks[i * num_task_per_batch:], ))

        p = mp.Pool(processes=num_cores)
        all_summary = p.starmap(doi_match_a_batch_by_csv, parallel_arguments)
        p.close()
        p.join()


if __name__ == '__main__':
    db = get_mongo_db('../config.json')
    print(db.collection_names())

    # doi_existence_stat(db)

    # foo(db, num_cores=8)

    bar(db, num_cores=8)