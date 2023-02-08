import numpy as np
import os
from datetime import date, datetime
from django.conf import settings
from zoneinfo import ZoneInfo

TOTAL_WINDOW = 50

PCT_HIGHEST_CBF = 0.4
PCT_LOWEST_CBF = 0.1

TOTAL_HIGHEST_CBF_ONLY = int(TOTAL_WINDOW * PCT_HIGHEST_CBF * 2) # 50 * 0.4 * 2 = 40
TOTAL_LOWEST_CBF_ONLY = int(TOTAL_WINDOW * PCT_LOWEST_CBF * 2) # 50 * 0.1 * 2 = 10

TOTAL_HIGHEST_CBF = int(TOTAL_WINDOW * PCT_HIGHEST_CBF) # 50 * 0.4 = 20
TOTAL_LOWEST_CBF = int(TOTAL_WINDOW * PCT_LOWEST_CBF) # 50 * 0.1 = 5

PCT_HIGHEST_UCF = 0.4
PCT_LOWEST_UCF = 0.1

TOTAL_HIGHEST_UCF = int(TOTAL_WINDOW * PCT_HIGHEST_UCF) # 50 * 0.4 = 20
TOTAL_LOWEST_UCF = int(TOTAL_WINDOW * PCT_LOWEST_UCF) # 50 * 0.1 = 5

TOTAL_HIGHEST_ALS_ONLY = int(TOTAL_WINDOW * PCT_HIGHEST_UCF * 2) # 50 * 0.4 * 2 = 40
TOTAL_LOWEST_ALS_ONLY = int(TOTAL_WINDOW * PCT_LOWEST_UCF * 2) # 50 * 0.1 * 2 = 10

BUFFER_LENGTH = 10

# Requirement for changing recommendation from CBF Only to Hybrid
MINIMUM_EACH_USER_EVENT_REQUIREMENT = 5 if settings.DEVELOPMENT_MODE else 15
MINIMUM_USER_REQUIREMENT = 5 if settings.DEVELOPMENT_MODE else 20

REFRESH_RECSYS_MINUTE = 10 if settings.DEVELOPMENT_MODE else 100
REFRESH_RECSYS_DAYS = 0

EVENT_TYPE_STRENGTH = {
    'CLICK': 1.0,
    'LIKE': 2.0, 
    'VIEW': 3.0,
}

LOCAL_TZ = ZoneInfo('Asia/Bangkok')

def get_today():
    """Get Today's Date with `YYYY-MM-DD` Format"""
    today = datetime.now(LOCAL_TZ)
    return date(today.year, today.month, today.day)


SAVE_LOG_PATH = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, 'website_logs' + os.sep)
LOG_FILENAME = str(get_today()) + '.txt'

def print_help(var, title='', username='', show_list_more=False, save_log_path=SAVE_LOG_PATH, log_filename = LOG_FILENAME):
    """Log to CLI and Save to File \n
    `============================================`\n
    `2023-01-06 14:15:01.963270`\n
    `USERNAME:  TRAIN APRIORI MODEL`\n
    `APRIORI MODEL`\n
    `============================================`
    
    `============================================`\n
    `2023-01-06 14:15:01.923290`\n
    `USERNAME:  TRAIN WEIGHTED MATRIX`\n
    `CBF LOWEST ITEM LIST`\n
    `[ [841, 2.82], [840, 2.95], [2237, 3.03], [834, 3.2], [224, 3.23] ]`\n
    `ORIGINAL LENGTH : 5`\n
    `============================================`
    """
    logs = []
    bracket = '============================================'
    print(bracket)
    print(datetime.now())
    print('USERNAME: ', username)

    logs += [bracket, str(datetime.now()), f'USERNAME: {str(username)}']
    
    if isinstance(var, str) and title == '':
        print(var)
        print(bracket)
        logs += [str(var), bracket]
    else:
        print(title)
        modified_var = var
        if not show_list_more and isinstance(var, list):
            modified_var = modified_var[:5] if len(modified_var) > 5 else modified_var
        
        print(modified_var)
        logs += [str(title), str(modified_var)]

        try:
            print(f'ORIGINAL LENGTH : {len(var)}')
            print(bracket)
            logs += [f'ORIGINAL LENGTH : {str(len(var))}', bracket]
        except TypeError as e:
            print(bracket)
            logs += [bracket]

    logs = '\n'.join(logs)

    if not settings.DEVELOPMENT_MODE:
        save_log(logs=logs, save_log_path=save_log_path, log_filename=log_filename)

def save_log(logs, save_log_path, log_filename):
    """Save Log File to Path and Create Directories If Not Exists"""
    if not os.path.exists(save_log_path):
        os.makedirs(save_log_path)

    with open(save_log_path + log_filename, 'a') as file:
        file.write(logs)

    file.close()
def mean_reciprocal_rank(rs):
    """Score is reciprocal of the rank of the first relevant item
    First element is 'rank 1'.  Relevance is binary (nonzero is relevant).
    Example from http://en.wikipedia.org/wiki/Mean_reciprocal_rank
    >>> rs = [[0, 0, 1], [0, 1, 0], [1, 0, 0]]
    >>> mean_reciprocal_rank(rs)
    0.61111111111111105
    >>> rs = np.array([[0, 0, 0], [0, 1, 0], [1, 0, 0]])
    >>> mean_reciprocal_rank(rs)
    0.5
    >>> rs = [[0, 0, 0, 1], [1, 0, 0], [1, 0, 0]]
    >>> mean_reciprocal_rank(rs)
    0.75
    Args:
        rs: Iterator of relevance scores (list or numpy) in rank order
            (first element is the first item)
    Returns:
        Mean reciprocal rank
    """
    rs = (np.asarray(r).nonzero()[0] for r in rs)
    return np.mean([1. / (r[0] + 1) if r.size else 0. for r in rs])


def mrr_at_k(rs):
    mrr_score = [ (1.0 / (float(score) + 1)) if score >= 0 else 0 for score in rs ]
    return float(sum(mrr_score)/len(rs))

def r_precision(r):
    """Score is precision after all relevant documents have been retrieved
    Relevance is binary (nonzero is relevant).
    >>> r = [0, 0, 1]
    >>> r_precision(r)
    0.33333333333333331
    >>> r = [0, 1, 0]
    >>> r_precision(r)
    0.5
    >>> r = [1, 0, 0]
    >>> r_precision(r)
    1.0
    Args:
        r: Relevance scores (list or numpy) in rank order
            (first element is the first item)
    Returns:
        R Precision
    """
    r = np.asarray(r) != 0
    z = r.nonzero()[0]
    if not z.size:
        return 0.
    return np.mean(r[:z[-1] + 1])


def precision_at_k(r, k):
    """Score is precision @ k
    Relevance is binary (nonzero is relevant).
    >>> r = [0, 0, 1]
    >>> precision_at_k(r, 1)
    0.0
    >>> precision_at_k(r, 2)
    0.0
    >>> precision_at_k(r, 3)
    0.33333333333333331
    >>> precision_at_k(r, 4)
    Traceback (most recent call last):
        File "<stdin>", line 1, in ?
    ValueError: Relevance score length < k
    Args:
        r: Relevance scores (list or numpy) in rank order
            (first element is the first item)
    Returns:
        Precision @ k
    Raises:
        ValueError: len(r) must be >= k
    """
    assert k >= 1
    r = np.asarray(r)[:k] != 0
    if r.size != k:
        raise ValueError('Relevance score length < k')
    return np.mean(r)


def average_precision(r):
    """Score is average precision (area under PR curve)
    Relevance is binary (nonzero is relevant).
    >>> r = [1, 1, 0, 1, 0, 1, 0, 0, 0, 1]
    >>> delta_r = 1. / sum(r)
    >>> sum([sum(r[:x + 1]) / (x + 1.) * delta_r for x, y in enumerate(r) if y])
    0.7833333333333333
    >>> average_precision(r)
    0.78333333333333333
    Args:
        r: Relevance scores (list or numpy) in rank order
            (first element is the first item)
    Returns:
        Average precision
    """
    r = np.asarray(r) != 0
    out = [precision_at_k(r, k + 1) for k in range(r.size) if r[k]]
    if not out:
        return 0.
    return np.mean(out)


def mean_average_precision(rs):
    """Score is mean average precision
    Relevance is binary (nonzero is relevant).
    >>> rs = [[1, 1, 0, 1, 0, 1, 0, 0, 0, 1]]
    >>> mean_average_precision(rs)
    0.78333333333333333
    >>> rs = [[1, 1, 0, 1, 0, 1, 0, 0, 0, 1], [0]]
    >>> mean_average_precision(rs)
    0.39166666666666666
    Args:
        rs: Iterator of relevance scores (list or numpy) in rank order
            (first element is the first item)
    Returns:
        Mean average precision
    """
    return np.mean([average_precision(r) for r in rs])


def dcg_at_k(r, k, method=0):
    """Score is discounted cumulative gain (dcg)
    Relevance is positive real values.  Can use binary
    as the previous methods.
    Example from
    http://www.stanford.edu/class/cs276/handouts/EvaluationNew-handout-6-per.pdf
    >>> r = [3, 2, 3, 0, 0, 1, 2, 2, 3, 0]
    >>> dcg_at_k(r, 1)
    3.0
    >>> dcg_at_k(r, 1, method=1)
    3.0
    >>> dcg_at_k(r, 2)
    5.0
    >>> dcg_at_k(r, 2, method=1)
    4.2618595071429155
    >>> dcg_at_k(r, 10)
    9.6051177391888114
    >>> dcg_at_k(r, 11)
    9.6051177391888114
    Args:
        r: Relevance scores (list or numpy) in rank order
            (first element is the first item)
        k: Number of results to consider
        method: If 0 then weights are [1.0, 1.0, 0.6309, 0.5, 0.4307, ...]
                If 1 then weights are [1.0, 0.6309, 0.5, 0.4307, ...]
    Returns:
        Discounted cumulative gain
    """
    r = np.asfarray(r)[:k]
    if r.size:
        if method == 0:
            return r[0] + np.sum(r[1:] / np.log2(np.arange(2, r.size + 1)))
        elif method == 1:
            return np.sum(r / np.log2(np.arange(2, r.size + 2)))
        else:
            raise ValueError('method must be 0 or 1.')
    return 0.


def ndcg_at_k(r, k, method=0):
    """Score is normalized discounted cumulative gain (ndcg)
    Relevance is positive real values.  Can use binary
    as the previous methods.
    Example from
    http://www.stanford.edu/class/cs276/handouts/EvaluationNew-handout-6-per.pdf
    >>> r = [3, 2, 3, 0, 0, 1, 2, 2, 3, 0]
    >>> ndcg_at_k(r, 1)
    1.0
    >>> r = [2, 1, 2, 0]
    >>> ndcg_at_k(r, 4)
    0.9203032077642922
    >>> ndcg_at_k(r, 4, method=1)
    0.96519546960144276
    >>> ndcg_at_k([0], 1)
    0.0
    >>> ndcg_at_k([1], 2)
    1.0
    Args:
        r: Relevance scores (list or numpy) in rank order
            (first element is the first item)
        k: Number of results to consider
        method: If 0 then weights are [1.0, 1.0, 0.6309, 0.5, 0.4307, ...]
                If 1 then weights are [1.0, 0.6309, 0.5, 0.4307, ...]
    Returns:
        Normalized discounted cumulative gain
    """
    dcg_max = dcg_at_k(sorted(r, reverse=True), k, method)
    if not dcg_max:
        return 0.
    return dcg_at_k(r, k, method) / dcg_max
