# Import Function from .views
from .views import print_help, create_random_recommendation
from .helper import *
from .models import Log, Distance, Recommendation, User

from django.db.models import Q
from django.http import JsonResponse

from joblib import dump as dump_model, load as load_model
from scipy.sparse import coo_matrix
from implicit.als import AlternatingLeastSquares
from implicit.nearest_neighbours import bm25_weight
from efficient_apriori import apriori
from sklearn.preprocessing import MinMaxScaler

import os, platform
import pandas as pd
import math
from datetime import datetime
from zoneinfo import ZoneInfo

def creation_date(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    """
    if platform.system() == 'Windows':
        return os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            return stat.st_birthtime
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            return stat.st_mtime

def combine_ucf_recommendation(recsys_1, recsys_2, limit = 100):
    combined_recommendation = []
    # Iterate 2 recsys simultaneously
    for recsys_a, recsys_b in zip(recsys_1, recsys_2):
        # If limit reached, break
        if len(combined_recommendation) >= limit:
            break

        # If score recsys_a is bigger than recsys_b then [ recsys_a, recsys_b ] and vice versa
        tmp = [ [recsys_b[0],recsys_b[1]] , [recsys_a[0],recsys_a[1]] ]  if recsys_b[1] > recsys_a[1] else [ [recsys_a[0],recsys_a[1]], [recsys_b[0],recsys_b[1]] ]
        combined_recommendation.extend(tmp)

    # If one recsys produce more than the other, the leftover is extended into array
    if len(combined_recommendation) < limit:
        tmp = [ x for x in recsys_2[len(recsys_1):] ] if len(recsys_1) < len(recsys_2) else [ x for x in recsys_1[len(recsys_2):] ]
        combined_recommendation.extend(tmp)

    return combined_recommendation

def train_als_model(user_id, is_refresh_time_based):
    print_help(var='ALS MODEL', username='TRAIN ALS MODEL')

    ucf_logs = Log.objects.all()

    # Get ids, product_ids, event_types, timestamp_deltas
    ucf_user_ids, ucf_product_ids, ucf_event_types, ucf_timestamp_deltas = [], [], [], []
    for record in ucf_logs:
        ucf_user_ids.append(record.user_id)
        ucf_product_ids.append(record.product_id)
        ucf_event_types.append(record.event_type)
        ucf_timestamp_deltas.append(record.timestamp_delta)
    
    data_ucf = {'user_id':ucf_user_ids,
                'product_id': ucf_product_ids,
                'event_type': ucf_event_types,
                'timestamp_delta': ucf_timestamp_deltas }

    ucf_df = pd.DataFrame(data=data_ucf)

    # Add Event Strength
    ucf_df['event_strength'] = ucf_df['event_type'].apply(lambda x: EVENT_TYPE_STRENGTH[x])

    # Group UCF By user_id and product_id and sum the event_strength
    ucf_grouped_df = ucf_df.groupby(['user_id','product_id']).sum().reset_index()
    print('============================================')
    print(ucf_grouped_df)
    print('============================================')

    # Construct product_ids, user_ids, and event_strength to coo_matrix (Coordinate Matrix)
    ucf_matrix_product_ids = ucf_grouped_df['product_id']
    ucf_matrix_user_ids = ucf_grouped_df['user_id']
    ucf_matrix_event_strength = ucf_grouped_df['event_strength']

    # Make Coordinate Matrix
    product_user_matrix = coo_matrix((ucf_matrix_event_strength, (ucf_matrix_product_ids, ucf_matrix_user_ids)))
    product_user_matrix = bm25_weight(product_user_matrix, K1=100, B=0.8)

    # Transpose product_user_matrix to user_product_matrix
    user_product_matrix = product_user_matrix.T.tocsr()

    # Use Already Existed Model if Path Exists and Create One if Doesn't
    dirname = os.path.dirname(__file__)
    up_two_levels = os.pardir + os.sep + os.pardir
    filename = 'als_model.sav'
    dest_path = os.path.join(dirname, up_two_levels, filename)
    
    ucf_model = None
    
    if os.path.exists(dest_path) and not is_refresh_time_based:
        
        print_help(var='LOAD UCF MODEL', username='TRAIN ALS MODEL')

        ucf_model = load_model(dest_path)

    else:
        print_help(var='TRAINING UCF MODEL', username='TRAIN ALS MODEL')
        
        # Train UCF Model
        ucf_model = AlternatingLeastSquares(factors=64, regularization=0.05)
        ucf_model.fit(2 * user_product_matrix)

        dump_model(ucf_model, dest_path)

    epoch_time = creation_date(dest_path)
    current_time = datetime.fromtimestamp(epoch_time)
    zone_time = current_time.astimezone(ZoneInfo('Asia/Bangkok')) 
    
    print_help(var=creation_date(dest_path), title='EPOCH TIME CREATION OR MODIFIED DATE FILE', username='SERVER TRAINING')
    print_help(var=current_time, title='CURRENT TIME CREATION OR MODIFIED DATE FILE', username='SERVER TRAINING')
    print_help(var=zone_time, title='ZONE TIME CREATION OR MODIFIED DATE FILE', username='SERVER TRAINING')
    
    
    ids, scores = ucf_model.recommend(user_id, user_product_matrix[user_id], N=50, filter_already_liked_items=False)

    # Save ids and score from recommendation in the form of tuple (id, score)
    ALS_result = [ (_id, score) for _id, score in zip(ids.tolist(), scores.tolist())]

    print_help(ALS_result, 'ALS RESULT', 'TRAIN ALS MODEL')
    
    return ALS_result

def train_apriori_model(apriori_unique_user_ids):
    print_help(var='APRIORI MODEL', username='TRAIN APRIORI MODEL')
    
    # Separate ids by user_id 
    # apriori_product_ids = [ [1,2], [3,4,5], [7,8] ]
    apriori_product_ids = []
    for _id in apriori_unique_user_ids:
        user_log_object = Log.objects.filter(event_type= 'VIEW',user_id = _id)
        tmp_product = []
        for record in user_log_object:
            tmp_product.append(record.product_id)
        apriori_product_ids.append(tmp_product)

    # Train Apriori
    _, rules = apriori(transactions=apriori_product_ids, 
                    min_support=0.03, 
                    min_confidence=0.2)

    # Convert to pandas.DataFrame
    df = pd.DataFrame(rules)
    results = df.iloc[:40]
    
    APRIORI_result = []
    for i in range(len(results)):
        APRIORI_result += [(rules[i].rhs[0], rules[i].confidence)]
    
    print_help(APRIORI_result, 'APRIORI RESULT', username='TRAIN APRIORI MODEL')

    return APRIORI_result

def train_weighted_matrix(user_id , total_highest_cbf = TOTAL_HIGHEST_CBF, total_lowest_cbf = TOTAL_LOWEST_CBF):
    print_help(var='WEIGHTED MATRIX MODEL', username='TRAIN WEIGHTED MATRIX')

    cbf_logs = Log.objects.filter(user_id = user_id)
    # Get product ids, event_types, timestamp_deltas
    cbf_product_ids, cbf_event_types, cbf_timestamp_deltas = [], [], []
    for record in cbf_logs:
        cbf_product_ids.append(record.product_id)
        cbf_event_types.append(record.event_type)
        cbf_timestamp_deltas.append(record.timestamp_delta)
    
    data_cbf = {'product_id': cbf_product_ids,
                'event_type': cbf_event_types,
                'timestamp_delta': cbf_timestamp_deltas }

    cbf_df = pd.DataFrame(data=data_cbf)

    # Add Event Strength to CBF
    cbf_df['event_strength'] = cbf_df['event_type'].apply(lambda x: EVENT_TYPE_STRENGTH[x])

    cbf_grouped_df = cbf_df.groupby(['product_id']).sum().reset_index()

    print('============================================')
    print(cbf_grouped_df)
    print('============================================')


    cbf_product_ids = cbf_grouped_df['product_id'].values.tolist()
    product_strengths = cbf_grouped_df['event_strength'].values.tolist()

    NAME_FEATURE = True
    PRICE_FEATURE = True
    DESCRIPTION_FEATURE = False
    MATERIAL_FEATURE = True
    WEIGHT_FEATURE = True
    DIMENSION_FEATURE = True
    FURNITURE_LOCATION_FEATURE = True
    FEATURES = [
        'NAME' if NAME_FEATURE else '',
        'PRICE' if PRICE_FEATURE else '',
        'DESCRIPTION' if DESCRIPTION_FEATURE else '',
        'MATERIAL' if MATERIAL_FEATURE else '',
        'WEIGHT' if WEIGHT_FEATURE else '',
        'DIMENSION' if DIMENSION_FEATURE else '',
        'FURNITURE_LOCATION' if FURNITURE_LOCATION_FEATURE else '',
    ]
    FEATURES = [ f for f in FEATURES if f != '' ]
    FEATURES = '=='.join(FEATURES)

    for _id in cbf_product_ids:
        distance_object = Distance.objects.filter(Q(product_id =_id) | Q(other_product_id = _id))[:1]
        
        if distance_object[0].feature_added == FEATURES and distance_object[0].temp_distance != 99.0:
            print('CONTINUE')
            continue
        
        else:
            distance_object = Distance.objects.filter(Q(product_id =_id) | Q(other_product_id = _id))

            for obj in distance_object:
                minus = 0

                if not NAME_FEATURE:
                    minus += obj.name_distance
                if not PRICE_FEATURE:
                    minus += obj.price_distance
                if not DESCRIPTION_FEATURE:
                    minus += obj.description_distance
                if not MATERIAL_FEATURE:
                    minus += obj.material_distance
                if not WEIGHT_FEATURE:
                    minus += obj.weight_distance
                if not DIMENSION_FEATURE:
                    minus += obj.dimension_distance
                if not FURNITURE_LOCATION_FEATURE:
                    minus += obj.furniture_location_distance

                obj.temp_distance = obj.total_distance - minus
                obj.feature_added = FEATURES
                obj.save()


    cbf_highest_item_list = []
    cbf_lowest_item_list = []
    cbf_total_strength = sum(product_strengths)
    
    print_help(var='FILTERING UCF', username='TRAIN WEIGHTED MATRIX')
    
    for count, _id in enumerate(cbf_product_ids):
        limit_highest = math.ceil(total_highest_cbf * product_strengths[count] / cbf_total_strength) + BUFFER_LENGTH
        limit_lowest = math.ceil(total_lowest_cbf * product_strengths[count] / cbf_total_strength) + BUFFER_LENGTH

        highest_distance_object = Distance.objects.filter(Q(product_id =_id) | Q(other_product_id = _id)).order_by('-temp_distance')[:limit_highest]
        lowest_distance_object = Distance.objects.filter(Q(product_id =_id) | Q(other_product_id = _id)).order_by('temp_distance')[:limit_lowest]

        for obj in highest_distance_object:
            if obj.product_id == _id:
                cbf_highest_item_list.append([obj.other_product_id, float(obj.temp_distance)])
            else:
                cbf_highest_item_list.append([obj.product_id, float(obj.temp_distance)])

        for obj in lowest_distance_object:
            if obj.product_id == _id:
                cbf_lowest_item_list.append([obj.other_product_id, float(obj.temp_distance)])
            else:
                cbf_lowest_item_list.append([obj.product_id, float(obj.temp_distance)])
    
    # print_help(var='MINMAXSCALER UCF', username='TRAIN WEIGHTED MATRIX')
    
    scaler = MinMaxScaler(feature_range=[0,1])

    # print_help(var='REMOVE DUPLICATE UCF', username='TRAIN WEIGHTED MATRIX')
    
    # Remove Duplicate in highest_item_list and lowest_item_list
    cbf_highest_item_list = dict(cbf_highest_item_list)
    cbf_lowest_item_list = dict(cbf_lowest_item_list)

    # Remove Duplicate between highest_item_list and lowest_item_list
    cbf_highest_item_list = [[k, v] for k, v in cbf_highest_item_list.items() if k not in cbf_lowest_item_list or cbf_lowest_item_list[k] < v]
    cbf_lowest_item_list = [[k, v] for k, v in cbf_lowest_item_list.items() if k not in cbf_highest_item_list or cbf_highest_item_list[k] < v]

    # print_help(var='SORT UCF', username='TRAIN WEIGHTED MATRIX')
    
    # Sort highest_item_list and lowest_item_list and slice to appropriate size
    cbf_highest_item_list =  sorted(cbf_highest_item_list,key=lambda x: x[1], reverse=True)
    cbf_highest_item_list = cbf_highest_item_list[:total_highest_cbf]

    cbf_lowest_item_list =  sorted(cbf_lowest_item_list,key=lambda x: x[1])
    cbf_lowest_item_list = cbf_lowest_item_list[:total_lowest_cbf]
    
    # print_help(cbf_highest_item_list, 'CBF HIGHEST ITEM LIST', username='TRAIN WEIGHTED MATRIX')

    # print_help(cbf_lowest_item_list, 'CBF LOWEST ITEM LIST', username='TRAIN WEIGHTED MATRIX')

    # Add 2 list    
    norm_combine_cbf = cbf_highest_item_list + cbf_lowest_item_list

    # Make [1,2,3] to [ 1],[2],[3] ]
    norm_combine_cbf = [[x[1]] for x in norm_combine_cbf]

    # print_help(norm_combine_cbf, 'NORM COMBINE CBF', username='TRAIN WEIGHTED MATRIX')

    # Normalized CBF
    norm_combine_cbf = scaler.fit_transform(norm_combine_cbf)

    norm_highest_score = norm_combine_cbf[:total_highest_cbf]
    norm_lowest_score = norm_combine_cbf[total_highest_cbf:]

    for x, y in zip(norm_highest_score, cbf_highest_item_list):
        y[1] = x[0]

    for x, y in zip(norm_lowest_score, cbf_lowest_item_list):
        y[1] = x[0]

    print_help(cbf_highest_item_list, 'CBF HIGHEST RECOMMENDATION', username='TRAIN WEIGHTED MATRIX')
    print_help(cbf_lowest_item_list, 'CBF LOWEST RECOMMENDATION', username='TRAIN WEIGHTED MATRIX')

    return cbf_highest_item_list, cbf_lowest_item_list


def train_model():
    is_show_score = True
    all_hybrid_recommendation = []
    
    unique_user = User.objects.all()
    
    print_help(unique_user,'UNIQUE USER', username='SERVER TRAINING')

    recommendations = Recommendation.objects.all()
    
    is_refresh_time_based = False
    if len(recommendations) > 0:
        local_tz = ZoneInfo('Asia/Bangkok')
        subtract_time = datetime.now(local_tz) - recommendations[0].created_at.astimezone(local_tz)
        
        print_help(recommendations[0].created_at.astimezone(local_tz), 'CREATED AT', username='SERVER TRAINING')
        print_help(datetime.now(local_tz), 'NOW', username='SERVER TRAINING')

        print('REFRESH RECSYS DIFFERENCE: {0} DAY(S), {1} MINUTE(S)'.format(subtract_time.days, subtract_time.seconds // 60))
        if subtract_time.days >= REFRESH_RECSYS_DAYS and (subtract_time.seconds // 60) >= REFRESH_RECSYS_MINUTE:
            is_refresh_time_based = True
            print_help(var='REFRESH RECSYS TIME BASED', username='SERVER TRAINING')
            

    if len(recommendations) <= 0 or is_refresh_time_based:

        for unique_user_obj in unique_user:
            print_help(var='TRAINING EVERY USER', username= unique_user_obj.username)

            cbf_logs = Log.objects.filter(user_id = unique_user_obj.id)

            print_help(cbf_logs, 'CBF LOGS', username='SERVER TRAINING')
            all_log_object = Log.objects.all()

            # Is User the Only One ?
            if len(unique_user) > 0 and len(cbf_logs) > 1:
                print_help(var='NOT RANDOM RECOMMENDATION', username='SERVER TRAINING')
                # Get ids, product_ids, event_types, timestamp_deltas
                user_ids, event_types = [], []
                for record in all_log_object:
                    user_ids.append(record.user_id)
                    event_types.append(record.event_type)
                
                data = {'user_id':user_ids,
                        'event_type': event_types }

                df = pd.DataFrame(data=data)
                df2 = df.groupby(['user_id'])['event_type'].count().reset_index()
                count_user_event = df2.values
                
                # Count User with Total Event Requirement > MINIMUM_EACH_USER_EVENT_REQUIREMENT
                count_event_requirement = 0
                for user_event in count_user_event:
                    if user_event[1] > MINIMUM_EACH_USER_EVENT_REQUIREMENT:
                        count_event_requirement += 1

                print_help(count_user_event, 'COUNT USER EVENT', username='SERVER TRAINING')
                print_help(count_event_requirement, 'COUNT EVENT REQUIREMENT', username='SERVER TRAINING')

                # If Total User and Log each User is below Requirement then just use CBF Only
                # CONTENT BASED FILTERING RECOMMENDATION
                if len(count_user_event) < MINIMUM_USER_REQUIREMENT and \
                    count_event_requirement < MINIMUM_EACH_USER_EVENT_REQUIREMENT:

                    print_help(var='CBF ONLY RECOMMENDATION', username='SERVER TRAINING')

                    # CBF FULL TOTAL WINDOW
                    cbf_highest_item_list, cbf_lowest_item_list = train_weighted_matrix(
                                                                        user_id=unique_user_obj.id,
                                                                        total_highest_cbf = TOTAL_HIGHEST_CBF_ONLY, 
                                                                        total_lowest_cbf = TOTAL_LOWEST_CBF_ONLY )
                    
                    all_hybrid_recommendation = combine_ucf_recommendation(
                                                        cbf_highest_item_list, 
                                                        cbf_lowest_item_list, 
                                                        limit = TOTAL_WINDOW )

                    print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION TESTING', username='SERVER TRAINING')
                else:
                    print_help(var='PARTIAL CBF RECOMMENDATION', username='SERVER TRAINING')
                    
                    # CBF 1/2 of TOTAL WINDOW
                    cbf_highest_item_list, cbf_lowest_item_list = train_weighted_matrix(
                                                                        user_id=unique_user_obj.id,
                                                                    total_highest_cbf = TOTAL_HIGHEST_CBF, 
                                                                    total_lowest_cbf = TOTAL_LOWEST_CBF )

                    filter_view_log = Log.objects.filter(event_type= 'VIEW')
                    apriori_unique_user_ids = list(dict.fromkeys([ record.user_id for record in filter_view_log ]))

                    # Apriori MUST HAVE more than 1 users with each user has to view more than 1 product
                    # Example user1 has to view at least 2 product AND user2 has to view at least 1 product

                    # USER BASED COLLABORATIVE FILTERING RECOMMENDATION
                    if len(filter_view_log) > 2 and len(apriori_unique_user_ids) > 1:

                        print_help(var='ALS AND APRIORI', username='SERVER TRAINING')
                        
                        # ALS METHOD
                        ALS_result = train_als_model(unique_user_obj.id, is_refresh_time_based)
                        
                        # APRIORI METHOD
                        APRIORI_result = train_apriori_model(apriori_unique_user_ids)

                        # Remove Duplicate from UCF and Apriori Recommendation
                        ALS_result = dict(ALS_result)
                        APRIORI_result = dict(APRIORI_result)

                        als_recommendation = [[k, v] for k, v in ALS_result.items() if k not in APRIORI_result or APRIORI_result[k] < v]
                        apriori_recommendation = [[k, v] for k, v in APRIORI_result.items() if k not in ALS_result or ALS_result[k] < v]

                        """ 
                        # Reminder #
                        PCT_HIGHEST_UCF = 0.4
                        PCT_LOWEST_UCF = 0.1
                        TOTAL_HIGHEST_UCF = TOTAL_WINDOW * PCT_HIGHEST_UCF
                        TOTAL_LOWEST_UCF = TOTAL_WINDOW * PCT_LOWEST_UCF
                        """
                        # Slice UCF Recommendation to Appropriate Size
                        als_highest_recommendation = als_recommendation[:int(TOTAL_HIGHEST_UCF) + BUFFER_LENGTH]
                        als_lowest_recommendation = als_recommendation[::-1][:int(TOTAL_LOWEST_UCF) + BUFFER_LENGTH]

                        # Slice Apriori Recommendation to Appropriate Size
                        apriori_highest_recommendation = apriori_recommendation[:int(TOTAL_HIGHEST_UCF) + BUFFER_LENGTH]
                        apriori_lowest_recommendation = apriori_recommendation[::-1][:int(TOTAL_LOWEST_UCF) + BUFFER_LENGTH]

                        print_help(als_highest_recommendation, 'ALS HIGHEST RECOMMENDATION', username='SERVER TRAINING')

                        print_help(als_lowest_recommendation, 'ALS LOWEST RECOMMENDATION', username='SERVER TRAINING')

                        print_help(apriori_highest_recommendation, 'APRIORI HIGHEST RECOMMENDATION', username='SERVER TRAINING')

                        print_help(apriori_lowest_recommendation, 'APRIORI LOWEST RECOMMENDATION', username='SERVER TRAINING')

                        # Combine UCF and Apriori
                        ucf_highest_item_list = combine_ucf_recommendation(als_highest_recommendation, apriori_highest_recommendation, limit= TOTAL_HIGHEST_UCF + BUFFER_LENGTH)
                        ucf_lowest_item_list = combine_ucf_recommendation(als_lowest_recommendation, apriori_lowest_recommendation , limit= TOTAL_LOWEST_UCF + BUFFER_LENGTH)
                        
                        # Add 2 list to Normalize each list's score
                        norm_combine_ucf = ucf_highest_item_list + ucf_lowest_item_list

                        # Change from [1,2,3] to [[1],[2],[3]]
                        norm_combine_ucf = [ [x[1]] for x in norm_combine_ucf]

                        scaler = MinMaxScaler(feature_range=[0,1])
                        norm_combine_ucf = scaler.fit_transform(norm_combine_ucf)

                        norm_highest_score = norm_combine_ucf[:len(ucf_highest_item_list)]
                        norm_lowest_score = norm_combine_ucf[len(ucf_highest_item_list):]

                        # Apply score to list
                        for x, y in zip(norm_highest_score, ucf_highest_item_list):
                            y[1] = x[0]

                        for x, y in zip(norm_lowest_score, ucf_lowest_item_list):
                            y[1] = x[0]

                        print_help(ucf_highest_item_list, 'COMBINE UCF HIGHEST RECOMMENDATION', username='SERVER TRAINING')

                        print_help(ucf_lowest_item_list, 'COMBINE UCF LOWEST RECOMMENDATION', username='SERVER TRAINING')

                    else:
                        print_help(var='ALS ONLY RECOMMENDATION', username='SERVER TRAINING')

                        # ALS METHOD
                        ALS_result = train_als_model(unique_user_obj.id, is_refresh_time_based)

                        # Slice ALS Recommendation to Appropriate Size
                        ucf_highest_item_list = ALS_result[:int(TOTAL_HIGHEST_ALS_ONLY) + BUFFER_LENGTH]
                        ucf_lowest_item_list = ALS_result[::-1][:int(TOTAL_LOWEST_ALS_ONLY) + BUFFER_LENGTH]

                        print_help(ucf_highest_item_list, 'ALS ONLY HIGHEST RECOMMENDATION', username='SERVER TRAINING')

                        print_help(ucf_lowest_item_list, 'ALS ONLY LOWEST RECOMMENDATION', username='SERVER TRAINING')

                    # HYBRID RECOMMENDATION

                    # Combine Highest UCF and CBF
                    hybrid_highest_item_list = combine_ucf_recommendation(ucf_highest_item_list, cbf_highest_item_list, limit= int((TOTAL_WINDOW * (PCT_HIGHEST_CBF + PCT_HIGHEST_UCF))) + BUFFER_LENGTH)
                    hybrid_lowest_item_list = combine_ucf_recommendation(ucf_lowest_item_list, cbf_lowest_item_list, limit= int((TOTAL_WINDOW * (PCT_LOWEST_CBF + PCT_LOWEST_UCF))) + BUFFER_LENGTH)

                    hybrid_highest_item_list = dict(hybrid_highest_item_list)
                    hybrid_lowest_item_list = dict(hybrid_lowest_item_list)

                    # Remove UCF id if id in Apriori and vice versa
                    hybrid_highest_item_list = [[k, v] for k, v in hybrid_highest_item_list.items() if k not in hybrid_lowest_item_list or hybrid_lowest_item_list[k] < v]
                    hybrid_lowest_item_list = [[k, v] for k, v in hybrid_lowest_item_list.items() if k not in hybrid_highest_item_list or hybrid_highest_item_list[k] < v]
                    
                    # Slice Hybrid Recommendation to Appropriate Size
                    hybrid_highest_item_list = hybrid_highest_item_list[ :int(TOTAL_WINDOW * (PCT_HIGHEST_CBF + PCT_HIGHEST_UCF))]
                    hybrid_lowest_item_list = hybrid_lowest_item_list[ :int(TOTAL_WINDOW * (PCT_LOWEST_CBF + PCT_LOWEST_UCF))]
                    
                    print_help(hybrid_highest_item_list, 'HYBRID HIGHEST RECOMMENDATION', username='SERVER TRAINING')

                    print_help(hybrid_lowest_item_list, 'HYBRID LOWEST RECOMMENDATION', username='SERVER TRAINING')

                    all_hybrid_recommendation = []

                    # Construct Recsys
                    co = 0
                    for i in range(len(hybrid_highest_item_list)):
                        item_list = hybrid_highest_item_list[i] if is_show_score else hybrid_highest_item_list[i][0]
                        all_hybrid_recommendation.append(item_list)

                        # Put Lowest Item every X Highest Item
                        # If Highest Item has 40 and Lowest Item has 10, Lowest Item is put every 4 Highest Item (i % 40/10 == 0)
                        if i % (len(hybrid_highest_item_list) // len(hybrid_lowest_item_list)) == 0 and co < len(hybrid_lowest_item_list):
                            item_list = hybrid_lowest_item_list[co] if is_show_score else hybrid_lowest_item_list[co][0]
                            all_hybrid_recommendation.append(item_list)

                            co += 1

                    print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION', username='SERVER TRAINING')

            else:
                # RANDOM RECOMMENDATION
                print_help(var='RANDOM RECOMMENDATION', username='SERVER TRAINING')
                all_hybrid_recommendation = create_random_recommendation()

            recommendation_object = Recommendation.objects.filter(user_id = unique_user_obj.id).order_by('rank')

            now = datetime.now(ZoneInfo('Asia/Bangkok'))

            if len(recommendation_object) <= 0:
                print_help(var='BULK CREATE', username='SERVER TRAINING')

                recommendations = []
                for count, item in enumerate(all_hybrid_recommendation, 1):
                    _id = item
                    if is_show_score:
                        _id = item[0]
                        
                    recommendations.append(Recommendation(user_id = unique_user_obj.id, 
                                                            product_id = _id, 
                                                            rank = count, 
                                                            created_at = now))

                # Bulk Create Recommendation
                Recommendation.objects.bulk_create(recommendations)

            else:
                print_help(var='BULK UPDATE', username='SERVER TRAINING')

                # Zip QuerySet Recommendation and All Hybrid Recommendation and Then Enumerate from 1
                for count, (rec, item) in enumerate(zip(recommendation_object, all_hybrid_recommendation), 1):
                    rec.product_id = item[0]
                    rec.rank = count
                    rec.created_at = now
                
                # Bulk Update Recommendation
                Recommendation.objects.bulk_update(recommendation_object, fields=['product_id','rank','created_at'])

        return JsonResponse({
            'message':'Done'
        })

    return JsonResponse({
        'message':'Not Yet'
    })
