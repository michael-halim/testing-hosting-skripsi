from django.shortcuts import render,redirect

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, PageNotAnInteger,EmptyPage
from django.shortcuts import get_object_or_404
from django.utils.datastructures import MultiValueDictKeyError

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView,View
from django.http import JsonResponse
from django.db.models import Q, Max, Min

from .forms import CreateUserForm
from .decorators import unauthenticated_user
from .models import Item, Log, Like, Distance, Recommendation, User, ItemDetail
from .helper import *

import math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from random import randint, randrange
from operator import or_
from functools import reduce

import pandas as pd
import re
from scipy.sparse import coo_matrix
from implicit.als import AlternatingLeastSquares
from implicit.nearest_neighbours import bm25_weight
from apyori import apriori
from sklearn.preprocessing import MinMaxScaler
from cryptography.fernet import Fernet
from .helper import *

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
MINIMUM_EACH_USER_EVENT_REQUIREMENT = 5
MINIMUM_USER_REQUIREMENT = 5

REFRESH_RECSYS_MINUTE = 100
REFRESH_RECSYS_DAYS = 0

def error_404_view(request, exception):
    # we add the path to the the 404.html file
    # here. The name of our HTML file is 404.html
    return render(request, '404.html')


def error_500_view(request):
    return render(request, '500.html')

def test_error_500(request):
    raise Exception('Make response code 500!')
    
class HomeView(LoginRequiredMixin, ListView):
    login_url = '/login/'
    redirect_field_name = '/'

    template_name = 'main_app/index.html'
    context_object_name = 'all_items'
    paginate_by = 25
    
    def post(self, request, *args, **kwargs):
        print('POST HOME VIEW')
        
        machine_learning(request)

        return redirect('main_app:home')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        item_object = Item.objects.all()
        colors = list(dict.fromkeys([ item.color for item in item_object if item.color != '' ]))

        print_help(colors, 'COLORS IN GET CONTEXT DATA')

        data['colors'] = colors

        user = User.objects.get(id = self.request.user.id)
        local_tz = ZoneInfo('Asia/Bangkok')
        diff = datetime.now(local_tz) - user.date_joined.astimezone(local_tz)
        print('USER MODAL DIFFERENCE: {0} DAY(S), {1} MINUTE(S)'.format(diff.days, diff.seconds // 60))

        # If it's still 1 minutes since creating an account, show modal
        is_show_modal = False        
        if diff.days <= 0 and (diff.seconds // 60) <= 1:
            is_show_modal = True

        print_help(True, 'IS SHOW MODAL INDEX')

        data['is_show_modal'] = is_show_modal
        data['request_path'] = self.request.path
        data['is_mobile'] = mobile(request=self.request)

        return data
        
    def get_queryset(self):
        """
        Timezone is Saved UTC+0 in DB, Here's how to change it to Local Timezone
        local_tz = ZoneInfo('Asia/Bangkok')
        db_tz = recommendations[0].created_at
        print(db_tz.astimezone(local_tz)) # UTC+7 because Asia/Bangkok is UTC+7
        """

        print_help('TAKE RECOMMENDATION FROM DB')
        recommendations = Recommendation.objects.filter(user_id = self.request.user.id).order_by('rank')
        
        is_refresh_time_based = False
        if len(recommendations) > 0:
            local_tz = ZoneInfo('Asia/Bangkok')
            subtract_time = datetime.now(local_tz) - recommendations[0].created_at.astimezone(local_tz)
            
            print_help(recommendations[0].created_at.astimezone(local_tz), 'CREATED AT')
            print_help(datetime.now(local_tz), 'NOW')
            print('REFRESH RECSYS DIFFERENCE: {0} DAY(S), {1} MINUTE(S)'.format(subtract_time.days, subtract_time.seconds // 60))
            if subtract_time.days >= REFRESH_RECSYS_DAYS and (subtract_time.seconds // 60) >= REFRESH_RECSYS_MINUTE:
                is_refresh_time_based = True
                print_help('REFRESH RECSYS TIME BASED')
                

        if len(recommendations) <= 0 or is_refresh_time_based:
            print_help('CREATE NEW RECOMMENDATIONS')
            machine_learning(self.request)
            recommendations = Recommendation.objects.filter(user_id = self.request.user.id).order_by('rank')


        # Get Recommended Product Ids
        recommended_product_ids = [ rec.product_id for rec in recommendations ]
        
        # Add Other Product Id that are not saved in Recommendation Table
        all_product_ids = Item.objects.all().values_list('id', flat=True)
        all_product_ids = list(all_product_ids)

        tmp = []
        for product_id in all_product_ids:
            if product_id not in recommended_product_ids:
                tmp.append(product_id)
        
        # Random Pop until X Value Remaining
        while len(tmp) > 6 * TOTAL_WINDOW:
            tmp.pop(randrange(len(tmp)))

        # Random Append to Recommended Product Ids
        while len(tmp) > 0:
            recommended_product_ids.append(tmp.pop(randrange(len(tmp))))

        print_help('BULK SELECT')

        # Select Item with Product Ids In Bulk
        recommendation_item = Item.objects.in_bulk(recommended_product_ids)

        # Select Recommended Item
        items = [ recommendation_item[product_id] for product_id in recommended_product_ids ]
        
        return items

class SearchView(LoginRequiredMixin, ListView):
    login_url = '/login/'
    redirect_field_name = '/'

    model = Item
    template_name = 'main_app/search.html'
    context_object_name = 'all_items'
    paginate_by = 20

    def get_queryset(self):
        q, km, kt, rm, rk, rt, dp, pd, js, hmin, hmax = '', '', '', '', '', '', '', '', '', '', ''
        search_furniture_location = []
        search_is_product = []

        """ 'if self.request.GET['something]' is called when it's empty, it will throw an error
            even when it's called in if statement
        """

        # Get Query
        try: q = self.request.GET['q']
        except MultiValueDictKeyError as e: print('Query is Empty')
            
        # Get Kamar Mandi Checkbox
        try: search_furniture_location += ['kamar mandi'] if self.request.GET['km'] else None
        except MultiValueDictKeyError as e: print('KM is Empty')
            
        # Get Kamar Tidur Checkbox
        try: search_furniture_location += ['kamar tidur'] if self.request.GET['kt'] else None
        except MultiValueDictKeyError as e: print('KT is Empty')
            
        # Get Ruang Makan Checkbox
        try: search_furniture_location += ['ruang makan'] if self.request.GET['rm'] else None
        except MultiValueDictKeyError as e: print('RM is Empty')
            
        # Get Ruang Keluarga Checkbox
        try: search_furniture_location += ['ruang keluarga'] if self.request.GET['rk'] else None
        except MultiValueDictKeyError as e: print('RK is Empty')
            
        # Get Ruang Tamu Checkbox
        try: search_furniture_location += ['ruang tamu'] if self.request.GET['rt'] else None
        except MultiValueDictKeyError as e: print('RT is Empty')
            
        # Get Dapur Checkbox
        try: search_furniture_location += ['dapur'] if self.request.GET['dp'] else None
        except MultiValueDictKeyError as e: print('DP is Empty')
            
        # Get isProduct Checkbox
        try: search_is_product += [1] if self.request.GET['pd'] else ''
        except MultiValueDictKeyError as e: print('PD is Empty')
            
        try: search_is_product += [0] if self.request.GET['js'] else ''
        except MultiValueDictKeyError as e: print('JS is Empty')
            
        # Get Price Hmin and Hmax Input and Replace '.' with '' 
        try: hmin = self.request.GET['hmin'].replace('.','') if self.request.GET['hmin'] else '' 
        except MultiValueDictKeyError as e: print('HMIN is Empty')
            
        try: hmax = self.request.GET['hmax'].replace('.','') if self.request.GET['hmax'] else '' 
        except MultiValueDictKeyError as e: print('HMAX is Empty')
            
        print_help(q, 'Query')
        print_help(km, 'CHECKBOX KAMAR MANDI')
        print_help(kt, 'CHECKBOX KAMAR TIDUR')
        print_help(rm, 'CHECKBOX RUANG MAKAN')
        print_help(rk, 'CHECKBOX RUANG KELUARGA')
        print_help(rt, 'CHECKBOX RUANG TAMU')
        print_help(dp, 'CHECKBOX DAPUR')
        print_help(pd, 'CHECKBOX PRODUK')
        print_help(js, 'CHECKBOX JASA')
        print_help(hmin, 'HARGA TERENDAH')
        print_help(hmax, 'HARGA TERTINGGI')

        # Construct Filter with Dyanmic Q() and Reduce
        # Make Alternative if Furniture Location is unchecked
        search_furniture_location = ['kamar mandi', 'kamar tidur', 'ruang makan', 'ruang keluarga', 'ruang tamu', 'dapur'] \
                                    if len(search_furniture_location) <= 0 else search_furniture_location

        print_help(search_furniture_location, 'SEARCH FURNITURE LOCATION')
        query_furniture_location = [ Q(furniture_location__icontains=w) for w in search_furniture_location ]
        reduce_query_furniture_location = reduce(or_, query_furniture_location)

        # Construct Filter with Dyanmic Q() and Reduce
        # Make Alternative if isProduct is unchecked
        print_help(search_is_product,'SEARCH IS PRODUCT')
        search_is_product = [1, 0] if len(search_is_product) <= 0 else search_is_product
        query_is_product = [ Q(isProduct__exact=w) for w in search_is_product ]
        reduce_query_is_product = reduce(or_, query_is_product)

        # Find Maximum and Minimum Price if Price is Left Unanswered
        aggregate_object = self.model.objects.all()
        min_price = aggregate_object.aggregate(Min('price'))['price__min']
        max_price = aggregate_object.aggregate(Max('price'))['price__max']
        
        hmin = min_price if hmin == '' or len(hmin) <= 0 else hmin
        hmax = max_price if hmax == '' or len(hmax) <= 0 else hmax

        # If Max Price is Lower than Min Price
        if int(hmax) < int(hmin):
            hmax = max_price

        test_query = self.model.objects.filter(reduce_query_furniture_location, reduce_query_is_product, 
                                        Q(name__icontains = q) | Q(description__icontains = q) | Q(additional_desc__icontains = q), 
                                        price__gte = hmin, price__lte=hmax )
        # Filter Item with Options and Make it to List so that it can be randomized
        items = list(self.model.objects.filter(reduce_query_furniture_location, reduce_query_is_product, 
                                        Q(name__icontains = q) | Q(description__icontains = q) | Q(additional_desc__icontains = q), 
                                        price__gte = hmin, price__lte=hmax ))
        print(test_query.query)
        # Randomized Position
        for i in range(len(items)):
            random_number = randint(0, len(items)-1)
            items[i], items[random_number] = \
                items[random_number], items[i]

        return items
class DetailPostView(LoginRequiredMixin,View):
    login_url = '/login/'
    redirect_field_name = '/'
    
    def get(self, request, slug, rank):
        print_help('ENTER DETAIL POST VIEWS')
        item = Item.objects.get(slug=slug)
        key = b'gAAAAABjXkfW2XopKy1P1GCvCcMJM2zjsnGQP0DatJo='
        fernet = Fernet(key)

        rank = fernet.decrypt(rank.encode('utf-8')).decode('utf-8')

        item_detail = ItemDetail.objects.filter(product_id = item.id)

        print_help(item_detail, 'ITEM DETAIL DETAIL PAGE')
        if len(item_detail) <= 0:
            create_item_detail = ItemDetail(product_id=item.id, 
                                            views=1,
                                            likes=0,
                                            see_original=0,
                                            copied_phone=0,
                                            copied_address=0)
            create_item_detail.save()

        else:
            item_detail[0].views += 1
            item_detail[0].save()


        # Log User With Event Type CLICK
        log = Log(user_id = request.user.id, 
                    event_type='CLICK', 
                    product_id = item.id, 
                    timestamp_in=datetime.now(ZoneInfo('Asia/Bangkok')),
                    rank = rank)
        log.save()

        has_liked = False
        if Like.objects.filter(user_id = request.user.id,product_id = item.id):
            has_liked = True

        context = {
            'item':item,
            'has_liked':has_liked
        }
        return render(request, 'main_app/detail.html',context)
class AboutView(LoginRequiredMixin,View):
    login_url = '/login/'
    redirect_field_name = '/'
    
    def get(self,request):
        context = {}
        return render(request, 'main_app/about.html',context)

class FavoriteView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = '/'

    def get(self,request):
        print_help('ENTER FAVORITE VIEWS')

        liked_item = Like.objects.filter(user_id=request.user.id)
        liked_item_ids = [ record.product_id  for record in liked_item ]

        item_object = Item.objects.in_bulk(liked_item_ids)
        all_items = [ item_object[item] for item in item_object ]

        p = Paginator(all_items, 20)  # creating a paginator object
    
        # getting the desired page number from url
        page_number = request.GET.get('page')
        try:
            # returns the desired page object
            page_obj = p.get_page(page_number)  
        except PageNotAnInteger:
            # if page_number is not an integer then assign the first page
            page_obj = p.page(1)
        except EmptyPage:
            # if page is empty then return last page
            page_obj = p.page(p.num_pages)

        
        print_help(all_items,'ALL FAVORITE ITEMS')        
        
        context = { 'page_obj':page_obj, 'all_items':all_items}

        return render(request, 'main_app/favorite.html',context)

def handle_copy(request):
    if request.POST:
        print_help('POST HANDLE COPY VIEWS')
        
        full_url = request.POST['current_url']
        
        # Get Slug from URL
        slug = full_url.split('/')[-2]

        # Get Item ID by Slug
        item = Item.objects.get(slug=slug)

        item_detail = ItemDetail.objects.get(product_id=item.id)

        if request.POST['type'] == 'PHONE':
            item_detail.copied_phone += 1
        elif request.POST['type'] == 'ADDRESS':
            item_detail.copied_address += 1
        
        item_detail.save()

        context = {
            'message':'success'
        }
        return JsonResponse(context)


    context = {
        'message':'error'
    }

    return JsonResponse(context)

@unauthenticated_user
def categoryPage(request,category):
    category = category.replace('-',' ')
    
    # Get All Recommendations Based On User ID
    recommendations = Recommendation.objects.filter(user_id=request.user.id)

    # Get All Recommendation ID and Get the Item to access furniture location
    recommended_product_ids = [ rec.product_id for rec in recommendations ]
    recommendation_item = Item.objects.in_bulk(recommended_product_ids)

    # Select Recommended Item
    recommended_ids = []    
    for product_id in recommended_product_ids:
        if recommendation_item[product_id].furniture_location == category:
            recommended_ids.append(product_id)

    # Add Other Product Id that are not saved in Recommendation Table
    all_category_ids = Item.objects.filter(furniture_location__contains=category).values_list('id', flat=True)
    all_category_ids = list(all_category_ids)

    not_recommended_ids = []
    for product_id in all_category_ids:
        if product_id not in recommended_ids:
            not_recommended_ids.append(product_id)
    
    # Random Pop until X Value Remaining
    while len(not_recommended_ids) > TOTAL_WINDOW :
        not_recommended_ids.pop(randrange(len(not_recommended_ids)))

    # Random Append to Recommended Product Ids
    while len(not_recommended_ids) > 0:
        recommended_ids.append(not_recommended_ids.pop(randrange(len(not_recommended_ids))))


    # Select Item with Product Ids In Bulk
    recommendation_item = Item.objects.in_bulk(recommended_ids)

    items = [ recommendation_item[product_id] for product_id in recommended_ids ]


    print_help(items, 'RECOMMENDED ITEMS BASED ON CATEGORY')

    p = Paginator(items, 20)  # creating a paginator object
    
    # getting the desired page number from url
    page_number = request.GET.get('page')
    try:
        # returns the desired page object
        page_obj = p.get_page(page_number)  
    except PageNotAnInteger:
        # if page_number is not an integer then assign the first page
        page_obj = p.page(1)
    except EmptyPage:
        # if page is empty then return last page
        page_obj = p.page(p.num_pages)

    context = {'page_obj': page_obj, 'item':items, 'category': category.title()}

    # sending the page object to index.html
    return render(request, 'main_app/category.html', context)

@unauthenticated_user
def loginPage(request):
    # margin-left: -50%; -> Signup Tab
    # margin-left: 0%; -> Login Tab
    margin_left = 0
    form = None
    input_username = ''
    print_help('ENTER LOGIN PAGE VIEWS')
    if request.method == 'POST':

        # Get Password and Confirm Password
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 is not None and password2 is not None:
            # Signup
            form = CreateUserForm(request.POST or None)
            margin_left = -50

            if form.is_valid():
                # Succesfuly Create User
                form.save()
                margin_left = 0
                messages.info(request,'Your Account Has Been Created')

        else:
            # Login
            username = request.POST.get('username')
            password = request.POST.get('password')

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect('main_app:home')

            # Error When Login
            messages.error(request,'Username or Password is incorrect')
            input_username = username
            margin_left = 0
            form = CreateUserForm()
    else:
        form = CreateUserForm()

    context = { 'form':form ,
                'margin_left':margin_left,
                'input_username':input_username, }

    return render(request,'main_app/login.html',context)

def logoutPage(request):
    logout(request)
    return redirect('main_app:login')


# Service to Update timestamp_out and timestamp_delta
@unauthenticated_user
def previousPage(request):
    # Get Current URL
    full_url = request.GET['current_url']
    
    # Get Slug from URL
    slug = full_url.split('/')[-2]
    
    # Get User ID
    user_id = request.user.id

    # Get Item ID by Slug
    item = Item.objects.get(slug=slug)
    item_id = item.id

    # Get Every Object with User ID and Product ID Matched
    # Then Add timestamp_out and time difference to DB
    for data in Log.objects.filter(user_id = user_id, product_id = item_id):
        data.timestamp_out = datetime.now(ZoneInfo('Asia/Bangkok'))
        diff = datetime.now(ZoneInfo('Asia/Bangkok')) - data.timestamp_in
        data.timestamp_delta = float(diff.total_seconds())
        data.save()

    data = {
        'message': 'success',
    }
    return JsonResponse(data)

def view_original_link(request):
    # Get Current URL
    full_url = request.GET['current_url']

    # Get Slug from URL
    slug = full_url.split('/')[-2]

    # Get Item ID by Slug
    item = Item.objects.get(slug=slug)

    now = datetime.now(ZoneInfo('Asia/Bangkok'))
    log = Log(user_id = request.user.id, 
                event_type='VIEW', 
                product_id = item.id, 
                timestamp_in = now,
                timestamp_out = now,
                timestamp_delta = 0.00)

    log.save()

    item_detail = ItemDetail.objects.filter(product_id = item.id)

    print_help(item_detail, 'ITEM DETAIL VIEW ORIGINAL LINK')
    if len(item_detail) <= 0:
        create_item_detail = ItemDetail(product_id=item.id, 
                                        views=1,
                                        likes=0,
                                        see_original=1,
                                        copied_phone=0,
                                        copied_address=0)
        create_item_detail.save()

    else:
        item_detail[0].see_original += 1
        item_detail[0].save()

    data = {
        'message': 'success',
        'redirect_url': item.original_link,
    }
    return JsonResponse(data)

def product_liked(request):

    if request.POST:
        # Get Current URL
        full_url = request.POST['current_url']
        print_help('PRODUCT LIKED VIEWS')
        # Get Slug from URL
        slug = full_url.split('/')[-2]

        # Get Item ID by Slug
        item = Item.objects.get(slug=slug)

        has_liked = True if request.POST['has_liked'] == 'True' else False

        item_detail = ItemDetail.objects.get(product_id = item.id)
        
        # If has liked then unlike, if not then like
        if has_liked: 
            print_help('DELETE LIKES')
            Like.objects.filter(user_id = request.user.id, product_id = item.id).delete()
            Log.objects.filter(user_id = request.user.id, event_type='LIKE', product_id = item.id).delete()

            # Subtract Likes in Item Detail
            item_detail.likes -= 1
            item_detail.save()

        else: 
            now = datetime.now(ZoneInfo('Asia/Bangkok'))
            Like(user_id = request.user.id, product_id = item.id).save()
            Log(user_id = request.user.id, 
                    event_type='LIKE', 
                    product_id = item.id, 
                    timestamp_in = now,
                    timestamp_out = now,
                    timestamp_delta = 0.00).save()

            # Add Likes in Item Detail
            item_detail.likes += 1
            item_detail.save()

        context = {
            'message': 'success',
            'has_liked':has_liked,
        }

        return render(request,'main_app/detail.html',context)

    context = {
        'message': 'unsuccessful',
    }

    return render(request,'main_app/detail.html',context)


def machine_learning(request):
    # EVENT TYPE WEIGHTING VALUE
    event_type_strength = {
        'CLICK': 1.0,
        'LIKE': 2.0, 
        'VIEW': 3.0,
    }

    unique_user = User.objects.all()
    
    print_help(unique_user,'UNIQUE USER')


    cbf_logs = Log.objects.filter(user_id = request.user.id)
    print_help(cbf_logs, 'CBF LOGS')
    
    is_show_score = True
    all_hybrid_recommendation = []

    # Is User the Only One ?
    if len(unique_user) > 0 and len(cbf_logs) > 1:
        print_help('NOT RANDOM RECOMMENDATION')

        all_log_object = Log.objects.all()

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

        # If Total User and Log each User is below Requirement then just use CBF Only
        # CONTENT BASED FILTERING RECOMMENDATION
        if len(count_user_event) < MINIMUM_USER_REQUIREMENT and count_event_requirement < MINIMUM_EACH_USER_EVENT_REQUIREMENT:
            print_help('CBF ONLY RECOMMENDATION')

            # CBF FULL TOTAL WINDOW
            cbf_highest_item_list, cbf_lowest_item_list = create_weighted_matrix_recommendation(
                                                            cbf_logs, 
                                                            event_type_strength, 
                                                            total_highest_cbf = TOTAL_HIGHEST_CBF_ONLY, 
                                                            total_lowest_cbf = TOTAL_LOWEST_CBF_ONLY )
            
            all_hybrid_recommendation = combine_ucf_recommendation(
                                            cbf_highest_item_list, 
                                            cbf_lowest_item_list, 
                                            limit = TOTAL_WINDOW )
            
            print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION CBF ONLY')
            
        else:
            print_help('PARTIAL CBF RECOMMENDATION')
            # CBF 1/2 of TOTAL WINDOW
            cbf_highest_item_list, cbf_lowest_item_list = create_weighted_matrix_recommendation( 
                                                            cbf_logs, 
                                                            event_type_strength, 
                                                            total_highest_cbf = TOTAL_HIGHEST_CBF, 
                                                            total_lowest_cbf = TOTAL_LOWEST_CBF )

            # Get Log that has been Viewed
            filter_view_log = Log.objects.filter(event_type= 'VIEW')
            apriori_unique_user_ids = list(dict.fromkeys([ record.user_id for record in filter_view_log ]))

            print_help(apriori_unique_user_ids,'apriori_unique_user_ids')

            # Apriori MUST HAVE more than 1 users with each user has to view more than 1 product
            # Example user1 has to view at least 2 product AND user2 has to view at least 1 product

            # USER BASED COLLABORATIVE FILTERING RECOMMENDATION
            if len(filter_view_log) > 2 and len(apriori_unique_user_ids) > 1:
                print_help('ALS AND APRIORI')
                # ALS METHOD
                ALS_result = create_als_recommendation(request=request, event_type_strength=event_type_strength)

                # APRIORI METHOD
                APRIORI_result = create_apriori_recommendation(apriori_unique_user_ids)

                # Remove Duplicate from UCF and Apriori Recommendation
                ALS_result = dict(ALS_result)
                APRIORI_result = dict(APRIORI_result)

                # Remove UCF id if id in Apriori and vice versa
                # This is to prevent duplication
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

                print_help(als_highest_recommendation, 'ALS HIGHEST RECOMMENDATION')

                print_help(als_lowest_recommendation, 'ALS LOWEST RECOMMENDATION')

                print_help(apriori_highest_recommendation, 'APRIORI HIGHEST RECOMMENDATION')

                print_help(apriori_lowest_recommendation, 'APRIORI LOWEST RECOMMENDATION')

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

                print_help(ucf_highest_item_list, 'COMBINE UCF HIGHEST RECOMMENDATION')

                print_help(ucf_lowest_item_list, 'COMBINE UCF LOWEST RECOMMENDATION')
            else:
                print_help('ALS ONLY RECOMMENDATION')

                # ALS METHOD
                ALS_result = create_als_recommendation(request=request, event_type_strength=event_type_strength)

                # Slice ALS Recommendation to Appropriate Size
                ucf_highest_item_list = ALS_result[:int(TOTAL_HIGHEST_ALS_ONLY) + BUFFER_LENGTH]
                ucf_lowest_item_list = ALS_result[::-1][:int(TOTAL_LOWEST_ALS_ONLY) + BUFFER_LENGTH]

                print_help(ucf_highest_item_list, 'ALS ONLY HIGHEST RECOMMENDATION')

                print_help(ucf_lowest_item_list, 'ALS ONLY LOWEST RECOMMENDATION')
            
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
            
            print_help(hybrid_highest_item_list, 'HYBRID HIGHEST RECOMMENDATION')

            print_help(hybrid_lowest_item_list, 'HYBRID LOWEST RECOMMENDATION')

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

            print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION')
        
    else:
        # RANDOM RECOMMENDATION
        print_help('RANDOM RECOMMENDATION')

        if request.POST:
            # Get POST Request
            post_dict = dict(request.POST)
            first_answer, second_answer, third_answer = [], [] ,[]
            is_answer_empty_count = 0

            try:
                first_answer = post_dict['first_answer[]']
            except KeyError as ke:
                print('First Answer is Empty')
                print(ke)
                is_answer_empty_count += 1
                
                first_answer = ['kamar tidur', 'kamar mandi', 'ruang makan', 'dapur', 'ruang keluarga', 'ruang tamu']

            try:
                second_answer = post_dict['second_answer[]']
            except KeyError as ke:
                print('Second Answer is Empty')
                print(ke)
                is_answer_empty_count += 1
                item_object = Item.objects.all()
                second_answer = list(dict.fromkeys([ item.color for item in item_object if item.color != '' ]))

            try:
                third_answer = post_dict['third_answer[]']

                # Change 1 or 0 for isProduct
                third_answer = [1 if answer == 'product' else 0 for answer in third_answer]

            except KeyError as ke:
                print('Third Answer is Empty')
                print(ke)
                is_answer_empty_count += 1
                third_answer = [1, 0]

            if is_answer_empty_count == 3: 
                # If All of the Question left Unanswered

                print_help('ALL QUESTION LEFT UNANSWERED')
                create_random_recommendation()

            else:
                # If One or More of the Question is Answered
                print_help(first_answer, 'FIRST ANSWER')
                print_help(second_answer, 'SECOND ANSWER')
                print_help(third_answer, 'THIRD ANSWER')

                # Construct Filter with Q()
                query_first_answer = [ Q(furniture_location__exact=w) for w in first_answer ]
                query_second_answer = [ Q(color__exact=w) for w in second_answer ]
                query_third_answer = [ Q(isProduct__exact=w) for w in third_answer ]
                
                # SELECT * FROM table WHERE (col_1 = 'a' OR col_1 = 'b') AND (col_2 = 'c' OR col_2 ='d') AND ....
                recommended_ids = Item.objects.filter(reduce(or_, query_first_answer), reduce(or_, query_second_answer), reduce(or_, query_third_answer))
                recommended_ids = [ rec.id for rec in recommended_ids ]

                # Add Random If Recommended Ids is less than Total Window, Or Slice if it's more than Total Window
                all_product_ids = Item.objects.all().values_list('id', flat=True)
                if len(recommended_ids) > TOTAL_WINDOW:
                    print_help('SLICE RECOMMENDED QUESTION')
                    recommended_ids = recommended_ids[ :TOTAL_HIGHEST_CBF_ONLY ]
                    count = Item.objects.count()
                    all_product_ids = []
                    for _ in range(2 * TOTAL_WINDOW):
                        # Fetching Random Item and Append it to Object and Give Score of 0 Because it is Random
                        item_object = Item.objects.all()[randint(0, count - 1)]
                        all_product_ids.append(item_object.id)


                all_product_ids = list(all_product_ids)

                not_recommended_ids = []
                for product_id in all_product_ids:
                    if product_id not in recommended_ids:
                        not_recommended_ids.append(product_id)
                
                # Random Pop until X Value Remaining
                while len(not_recommended_ids) > (TOTAL_WINDOW - TOTAL_HIGHEST_CBF_ONLY):
                    not_recommended_ids.pop(randrange(len(not_recommended_ids)))

                # Random Append to Recommended Product Ids
                while len(not_recommended_ids) > 0:
                    recommended_ids.append(not_recommended_ids.pop(randrange(len(not_recommended_ids))))


                # Randomized Position
                for i in range(len(recommended_ids)):
                    random_number = randint(0, len(recommended_ids)-1)
                    recommended_ids[i], recommended_ids[random_number] = \
                        recommended_ids[random_number], recommended_ids[i]
                
                
                all_hybrid_recommendation = []
                for rec_id in recommended_ids:
                    all_hybrid_recommendation.append([rec_id, 0.0])

                print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION WITH QUESTION')

        else:      
            # If Choose Not to Answer the Question
            all_hybrid_recommendation = create_random_recommendation()
            print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION RANDOM')

    recommendation_object = Recommendation.objects.filter(user_id = request.user.id).order_by('rank')

    now = datetime.now(ZoneInfo('Asia/Bangkok'))

    if len(recommendation_object) <= 0:
        print_help('BULK CREATE')

        recommendations = []
        for count, item in enumerate(all_hybrid_recommendation, 1):
            _id = item
            if is_show_score:
                _id = item[0]
                
            recommendations.append(Recommendation(user_id = request.user.id, 
                                                    product_id = _id, 
                                                    rank = count, 
                                                    created_at = now))

        # Bulk Create Recommendation
        Recommendation.objects.bulk_create(recommendations)
    else:
        print_help('BULK UPDATE')

        # Zip QuerySet Recommendation and All Hybrid Recommendation and Then Enumerate from 1
        for count, (rec, item) in enumerate(zip(recommendation_object, all_hybrid_recommendation), 1):
            rec.product_id = item[0]
            rec.rank = count
            rec.created_at = now
        
        # Bulk Update Recommendation
        Recommendation.objects.bulk_update(recommendation_object, fields=['product_id','rank','created_at'])

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

def create_random_recommendation(limit = TOTAL_WINDOW):
    count = Item.objects.count()
    all_hybrid_recommendation = []
    for _ in range(limit):
        # Fetching Random Item and Append it to Object and Give Score of 0 Because it is Random
        item_object = Item.objects.all()[randint(0, count - 1)]
        all_hybrid_recommendation.append([item_object.id, 0.0])

    return all_hybrid_recommendation

def create_weighted_matrix_recommendation(cbf_logs, event_type_strength, total_highest_cbf = TOTAL_HIGHEST_CBF, total_lowest_cbf = TOTAL_LOWEST_CBF):
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
    cbf_df['event_strength'] = cbf_df['event_type'].apply(lambda x: event_type_strength[x])

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
    
    for _id in cbf_product_ids:
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
            obj.save()

    cbf_highest_item_list = []
    cbf_lowest_item_list = []
    cbf_total_strength = sum(product_strengths)

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

    scaler = MinMaxScaler(feature_range=[0,1])

    # Remove Duplicate in highest_item_list and lowest_item_list
    cbf_highest_item_list = dict(cbf_highest_item_list)
    cbf_lowest_item_list = dict(cbf_lowest_item_list)

    # Remove Duplicate between highest_item_list and lowest_item_list
    cbf_highest_item_list = [[k, v] for k, v in cbf_highest_item_list.items() if k not in cbf_lowest_item_list or cbf_lowest_item_list[k] < v]
    cbf_lowest_item_list = [[k, v] for k, v in cbf_lowest_item_list.items() if k not in cbf_highest_item_list or cbf_highest_item_list[k] < v]

    # Sort highest_item_list and lowest_item_list and slice to appropriate size
    cbf_highest_item_list =  sorted(cbf_highest_item_list,key=lambda x: x[1], reverse=True)
    cbf_highest_item_list = cbf_highest_item_list[:total_highest_cbf]

    cbf_lowest_item_list =  sorted(cbf_lowest_item_list,key=lambda x: x[1])
    cbf_lowest_item_list = cbf_lowest_item_list[:total_lowest_cbf]
    
    print_help(cbf_highest_item_list,'CBF HIGHEST ITEM LIST')
    print_help(cbf_lowest_item_list,'CBF LOWEST ITEM LIST')

    # Add 2 list    
    norm_combine_cbf = cbf_highest_item_list + cbf_lowest_item_list

    # Make [1,2,3] to [ 1],[2],[3] ]
    norm_combine_cbf = [[x[1]] for x in norm_combine_cbf]

    print_help(norm_combine_cbf,'NORM COMBINE CBF')

    # Normalized CBF
    norm_combine_cbf = scaler.fit_transform(norm_combine_cbf)

    norm_highest_score = norm_combine_cbf[:total_highest_cbf]
    norm_lowest_score = norm_combine_cbf[total_highest_cbf:]

    for x, y in zip(norm_highest_score, cbf_highest_item_list):
        y[1] = x[0]

    for x, y in zip(norm_lowest_score, cbf_lowest_item_list):
        y[1] = x[0]

    print_help(cbf_highest_item_list, 'CBF HIGHEST RECOMMENDATION')

    print_help(cbf_lowest_item_list, 'CBF LOWEST RECOMMENDATION')

    return cbf_highest_item_list, cbf_lowest_item_list

def create_als_recommendation(request, event_type_strength):
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
    ucf_df['event_strength'] = ucf_df['event_type'].apply(lambda x: event_type_strength[x])

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

    # Train UCF Model
    ucf_model = AlternatingLeastSquares(factors=64, regularization=0.05)
    ucf_model.fit(2 * user_product_matrix)
    
    # Give UCF Recommendation based on logged in user
    user_id = request.user.id
    ids, scores = ucf_model.recommend(user_id, user_product_matrix[user_id], N=50, filter_already_liked_items=False)

    # Save ids and score from recommendation in the form of tuple (id, score)
    ALS_result = [ (_id, score) for _id, score in zip(ids.tolist(), scores.tolist())]

    return ALS_result

def create_apriori_recommendation(apriori_unique_user_ids):
    # Separate ids by user_id 
    # apriori_product_ids = [ [1,2], [3,4,5], [7,8] ]
    apriori_product_ids = []
    for _id in apriori_unique_user_ids:
        user_log_object = Log.objects.filter(event_type= 'VIEW',user_id = _id)
        tmp_product = []
        for record in user_log_object:
            tmp_product.append(record.product_id)
        apriori_product_ids.append(tmp_product)

    print_help(apriori_product_ids, 'APRIORI PRODUCT IDS')
    # Train Apriori
    rules = apriori(transactions=apriori_product_ids, 
                    min_support=0.03, 
                    min_confidence=0.2, 
                    min_lift=2,
                    min_length =2,
                    max_length =4)

    # Get Apriori Results
    results = list(rules)
    print_help(results, 'RESULT LIST RULES')
    apriori_df = pd.DataFrame(inspect(results), columns = ['Left Hand Side', 'Right Hand Side', 'Support', 'Confidence', 'Lift'])
    
    print('============================================')
    print('APRIORI DF')
    print(apriori_df)
    print('============================================')
    # Sorted by Confidence
    apriori_df = apriori_df.nlargest(n=40, columns='Confidence')

    # Get Apriori RHS and Confidence from df
    APRIORI_result = [ (_id, score) for _id, score in zip(apriori_df['Right Hand Side'].tolist(), apriori_df['Confidence'].tolist())]

    # Get unique ids from Apriori Recommendation
    apriori_recommend_df = list(dict.fromkeys( [ _id for _id, _ in APRIORI_result ] ))

    print_help(apriori_recommend_df, 'APRIORI RECOMMENDATION')

    return APRIORI_result

def inspect(results):
    lhs         = [tuple(result[2][0][0])[0] for result in results]
    rhs         = [tuple(result[2][0][1])[0] for result in results]
    supports    = [result[1] for result in results]
    confidences = [result[2][0][2] for result in results]
    lifts       = [result[2][0][3] for result in results]
    
    return list(zip(lhs, rhs, supports, confidences, lifts))

def print_help(var, title=''):
    print('============================================')
    if isinstance(var, str) and title == '':
        print(var)
        print('============================================')

    else:
        print(title)
        print(var)
        try:
            print(f'LENGTH : {len(var)}')
            print('============================================')
        except TypeError as e:
            print('============================================')

@login_required(login_url='main_app:home')
def ranking(request):
    if request.user.is_staff:

        try:
            start_at = '2022-12-16'
            end_at = '2022-12-22' 

            try: start_at =  request.GET['start_at'] if request.GET['start_at'] else None
            except MultiValueDictKeyError as e: print('start_at is undefined')

            try: end_at =  request.GET['end_at'] if request.GET['end_at'] else None
            except MultiValueDictKeyError as e: print('end_at is undefined')

            print_help(request.user.is_staff, 'REQUEST USER IS STAFF')

            users_object = User.objects.all()
            unique_user = list(dict.fromkeys([ record.id for record in users_object ]))
            
            print_help(unique_user,'UNIQUE USER')
            user_array = []
            for _id in unique_user:
                print_help(start_at, 'START AT')
                print_help(end_at, 'END AT')
                logs = Log.objects.filter(user_id = _id, event_type='CLICK', timestamp_in__range=[start_at, end_at])
                # Get ids, event_types, timestamp_deltas
                user_ids, product_ids, event_types, timestamp_deltas, ranks  = [], [], [], [], []
                for record in logs:
                    user_ids.append(record.user_id)
                    product_ids.append(record.product_id)
                    event_types.append(record.event_type)
                    timestamp_deltas.append(record.timestamp_delta)
                    ranks.append(record.rank)

                data = {'user_id':user_ids,
                        'product_id': product_ids,
                        'event_type': event_types,
                        'timestamp_delta': timestamp_deltas,
                        'rank':ranks }

                ranking_df = pd.DataFrame(data=data)

                print('LOG RANKING')
                print(ranking_df)

                print_help(ranks, 'RANKS CHOOSEN')

                mrr_score = mrr_at_k(ranks)
                print_help(mrr_score, 'MRR @ K')

                distinct_rank = list(dict.fromkeys([ rank for rank in ranks ]))
                print_help(distinct_rank, 'DISTINCT RANK')

                max_rank = max(distinct_rank)

                # binary_ndcg = [0] * TOTAL_WINDOW
                binary_ndcg = [0] * (max_rank + 1)

                for rank in distinct_rank:
                    binary_ndcg[rank] = 1

                print_help(binary_ndcg, 'BINARY NDCG')
                
                ndcg_score = ndcg_at_k(binary_ndcg, TOTAL_WINDOW, method = 1)
                print_help(ndcg_score, 'NDCG @ K')

                user_array.append([_id, mrr_score, ndcg_score])

        except ZeroDivisionError as zde:
            print(zde)

        for co, user_id in enumerate(user_array):
            u = users_object.filter(id=user_id[0])
            user_array[co].append(u[0].username)

        print(user_array)
        context = {'user_data':user_array}
        return render(request, 'main_app/ranking.html', context)
    else:
        return redirect('main_app:home')

def mobile(request):
    """Return True if the request comes from a mobile device."""

    MOBILE_AGENT_RE=re.compile(r".*(iphone|mobile|androidtouch)",re.IGNORECASE)

    if MOBILE_AGENT_RE.match(request.META['HTTP_USER_AGENT']):
        return True
    else:
        return False