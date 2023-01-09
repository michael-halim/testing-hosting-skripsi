from django.shortcuts import render,redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, PageNotAnInteger,EmptyPage
from django.utils.datastructures import MultiValueDictKeyError
from django.conf import settings

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView,View
from django.http import JsonResponse
from django.db.models import Q, Max, Min

from .forms import CreateUserForm
from .decorators import unauthenticated_user
from .models import Item, Log, Like, Distance, Recommendation, User, ItemDetail
from .helper import *

import math
from datetime import datetime
from zoneinfo import ZoneInfo
from random import randint, randrange
from operator import or_
from functools import reduce

import pandas as pd
import re
import os
from joblib import dump as dump_model, load as load_model
from scipy.sparse import coo_matrix
from implicit.als import AlternatingLeastSquares
from implicit.nearest_neighbours import bm25_weight
from efficient_apriori import apriori
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
MINIMUM_EACH_USER_EVENT_REQUIREMENT = 5 if settings.DEVELOPMENT_MODE else 15
MINIMUM_USER_REQUIREMENT = 5 if settings.DEVELOPMENT_MODE else 20

REFRESH_RECSYS_MINUTE = 10 if settings.DEVELOPMENT_MODE else 2
REFRESH_RECSYS_DAYS = 0

EVENT_TYPE_STRENGTH = {
    'CLICK': 1.0,
    'LIKE': 2.0, 
    'VIEW': 3.0,
}

def error_404_view(request, exception):
    # we add the path to the the 404.html file
    # here. The name of our HTML file is 404.html
    return render(request, '404.html')


def error_500_view(request):
    return render(request, '500.html')
    
class HomeView(LoginRequiredMixin, ListView):
    login_url = '/login/'
    redirect_field_name = '/'

    template_name = 'main_app/index.html'
    context_object_name = 'all_items'
    paginate_by = 25
    
    def post(self, request, *args, **kwargs):
        print('POST HOME VIEW')
        
        handle_question(request)

        return redirect('main_app:home')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        item_object = Item.objects.all()
        colors = list(dict.fromkeys([ item.color for item in item_object if item.color != '' ]))
        exception_word = ['natural', 'leather', 'olives', 'leopard', 'frame', 'lion', 'bengal', 'wolf', 'tibetan', 'menarik', 'disesuaikan', 'teak', 'invory']
        addition_word = ['natural']
        filtered_colors = []
        
        # If There's Any Word Contains In Exception Word Don't Include
        # Then Add Every Word in Addition Word
        for color in colors:
            if not any(x in color for x in exception_word):
                filtered_colors.append(color)

        filtered_colors += addition_word

        print_help(filtered_colors, 'COLORS IN GET CONTEXT DATA', username=self.request.user.username)

        data['colors'] = filtered_colors

        user = User.objects.get(id = self.request.user.id)
        local_tz = ZoneInfo('Asia/Bangkok')
        diff = datetime.now(local_tz) - user.date_joined.astimezone(local_tz)
        print('USER MODAL DIFFERENCE: {0} DAY(S), {1} MINUTE(S)'.format(diff.days, diff.seconds // 60))

        # If it's still 1 minutes since creating an account, show modal
        is_show_modal = False        
        if diff.days <= 0 and (diff.seconds <= 20):
            is_show_modal = True

        print_help(True, 'IS SHOW MODAL INDEX', username=self.request.user.username)

        data['is_show_modal'] = is_show_modal
        data['request_path'] = self.request.path
        data['is_mobile'] = mobile(request=self.request)

        return data
        
    def get_queryset(self):
        """
        Timezone is Saved UTC+0 in DB, Here's how to change it to Local Timezone \n
        `local_tz = ZoneInfo('Asia/Bangkok')` \n
        `db_tz = recommendations[0].created_at` \n
        `print(db_tz.astimezone(local_tz)) # UTC+7 because Asia/Bangkok is UTC+7`
        """

        print_help(var='TAKE RECOMMENDATION FROM DB', username=self.request.user.username)
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

        print_help(var='BULK SELECT', username=self.request.user.username)

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
            
        print_help(q, 'Query', username=self.request.user.username)
        print_help(km, 'CHECKBOX KAMAR MANDI', username=self.request.user.username)
        print_help(kt, 'CHECKBOX KAMAR TIDUR', username=self.request.user.username)
        print_help(rm, 'CHECKBOX RUANG MAKAN', username=self.request.user.username)
        print_help(rk, 'CHECKBOX RUANG KELUARGA', username=self.request.user.username)
        print_help(rt, 'CHECKBOX RUANG TAMU', username=self.request.user.username)
        print_help(dp, 'CHECKBOX DAPUR', username=self.request.user.username)
        print_help(pd, 'CHECKBOX PRODUK', username=self.request.user.username)
        print_help(js, 'CHECKBOX JASA', username=self.request.user.username)
        print_help(hmin, 'HARGA TERENDAH', username=self.request.user.username)
        print_help(hmax, 'HARGA TERTINGGI', username=self.request.user.username)

        # Construct Filter with Dyanmic Q() and Reduce
        # Make Alternative if Furniture Location is unchecked
        search_furniture_location = ['kamar mandi', 'kamar tidur', 'ruang makan', 'ruang keluarga', 'ruang tamu', 'dapur'] \
                                    if len(search_furniture_location) <= 0 else search_furniture_location

        print_help(search_furniture_location, 'SEARCH FURNITURE LOCATION', username=self.request.user.username)
        
        query_furniture_location = [ Q(furniture_location__icontains=w) for w in search_furniture_location ]
        reduce_query_furniture_location = reduce(or_, query_furniture_location)

        # Construct Filter with Dyanmic Q() and Reduce
        # Make Alternative if isProduct is unchecked
        print_help(search_is_product,'SEARCH IS PRODUCT', username=self.request.user.username)

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
        print_help(var='ENTER DETAIL POST VIEWS', username=request.user.username)
        item = Item.objects.get(slug=slug)
        key = b'gAAAAABjXkfW2XopKy1P1GCvCcMJM2zjsnGQP0DatJo='
        fernet = Fernet(key)

        rank = fernet.decrypt(rank.encode('utf-8')).decode('utf-8')

        item_detail = ItemDetail.objects.filter(product_id = item.id)

        print_help(item_detail, 'ITEM DETAIL DETAIL PAGE', username=request.user.username)
        if len(item_detail) <= 0:
            ItemDetail(product_id=item.id, 
                        views=1,
                        likes=0,
                        see_original=0,
                        copied_phone=0,
                        copied_address=0).save()

        else:
            item_detail[0].views += 1
            item_detail[0].save()


        # Log User With Event Type CLICK
        Log(user_id = request.user.id, 
            event_type='CLICK', 
            product_id = item.id, 
            timestamp_in=datetime.now(ZoneInfo('Asia/Bangkok')),
            rank = rank).save()

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
        print_help(var='ENTER FAVORITE VIEWS', username=request.user.username)

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

        
        print_help(all_items,'ALL FAVORITE ITEMS', username=request.user.username)
        
        context = { 'page_obj':page_obj, 'all_items':all_items}

        return render(request, 'main_app/favorite.html',context)

def handle_copy(request):
    if request.POST:
        print_help(var='POST HANDLE COPY VIEWS', username=request.user.username)
        
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


    print_help(items, 'RECOMMENDED ITEMS BASED ON CATEGORY', username=request.user.username)

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
    print_help(var='ENTER LOGIN PAGE VIEWS', username=request.user.username)
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
    Log(user_id = request.user.id, 
        event_type='VIEW', 
        product_id = item.id, 
        timestamp_in = now,
        timestamp_out = now,
        timestamp_delta = 0.00).save()
    
    item_detail = ItemDetail.objects.filter(product_id = item.id)

    print_help(item_detail, 'ITEM DETAIL VIEW ORIGINAL LINK', username=request.user.username)
    if len(item_detail) <= 0:
        ItemDetail(product_id=item.id, 
                    views=1,
                    likes=0,
                    see_original=1,
                    copied_phone=0,
                    copied_address=0).save()

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
        print_help(var='PRODUCT LIKED VIEWS', username=request.user.username)
        # Get Slug from URL
        slug = full_url.split('/')[-2]

        # Get Item ID by Slug
        item = Item.objects.get(slug=slug)

        has_liked = True if request.POST['has_liked'] == 'True' else False

        item_detail = ItemDetail.objects.get(product_id = item.id)
        
        # If has liked then unlike, if not then like
        if has_liked: 
            print_help(var='DELETE LIKES', username=request.user.username)
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


def handle_question(request):
    is_show_score = True
    all_hybrid_recommendation = []
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

            print_help(var='ALL QUESTION LEFT UNANSWERED', username=request.user.username)
            all_hybrid_recommendation = create_random_recommendation()

        else:
            # If One or More of the Question is Answered

            print_help(first_answer, 'FIRST ANSWER', username=request.user.username)
            print_help(second_answer, 'SECOND ANSWER', username=request.user.username)
            print_help(third_answer, 'THIRD ANSWER', username=request.user.username)

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
                print_help(var='SLICE RECOMMENDED QUESTION', username=request.user.username)
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

            print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION WITH QUESTION', username=request.user.username)

    else:      
        # If Choose Not to Answer the Question
        all_hybrid_recommendation = create_random_recommendation()
        print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION RANDOM', username=request.user.username)

    recommendation_object = Recommendation.objects.filter(user_id = request.user.id).order_by('rank')

    now = datetime.now(ZoneInfo('Asia/Bangkok'))

    if len(recommendation_object) <= 0:
        print_help(var='BULK CREATE', username=request.user.username)

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
        print_help(var='BULK UPDATE', username=request.user.username)

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

def print_help(var, title='', username=''):
    """
    Log Preview If Variable is String
    ============================================
    ============================================ \n
    2023-01-06 14:15:01.963270 \n
    USERNAME:  TRAIN APRIORI MODEL \n
    APRIORI MODEL\n
    ============================================

    Log Preview If Variable Is An Array
    ============================================
    ============================================\n
    2023-01-06 14:15:01.923290\n
    USERNAME:  TRAIN WEIGHTED MATRIX\n
    CBF LOWEST ITEM LIST\n
    [ [841, 2.82], [840, 2.95], [2237, 3.03], [834, 3.2], [224, 3.23] ]\n
    LENGTH : 5\n
    ============================================
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
        print(var)
        logs += [str(title), str(var)]

        try:
            print(f'LENGTH : {len(var)}')
            print(bracket)
            logs += [f'LENGTH : {str(len(var))}', bracket]
        except TypeError as e:
            print(bracket)
            logs += [bracket]

    logs = '\n'.join(logs)

    if settings.DEVELOPMENT_MODE:
        save_log(logs, filename='logs.txt')

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

            print_help(request.user.is_staff, 'REQUEST USER IS STAFF', username=request.user.username)

            users_object = User.objects.all()
            unique_user = list(dict.fromkeys([ record.id for record in users_object ]))
            
            print_help(unique_user,'UNIQUE USER', username=request.user.username)
            user_array = []
            for _id in unique_user:
                print_help(start_at, 'START AT', username=request.user.username)
                print_help(end_at, 'END AT', username=request.user.username)
                
                logs = Log.objects.filter(user_id = _id, event_type='CLICK', timestamp_in__range=[start_at, end_at])
                like_logs = Log.objects.filter(user_id= _id, event_type='LIKE', timestamp_in__range=[start_at, end_at])
                like_logs = [ log.product_id for log in like_logs ]
                like_ranks = []

                for item_id in like_logs:
                    recommended_item = Recommendation.objects.filter(user_id=_id, product_id=item_id)
                    if len(recommended_item) <= 0:
                        like_ranks.append(int(TOTAL_WINDOW) + 1)
                    elif len(recommended_item) == 1:
                        like_ranks.append(recommended_item[0].rank)

                avg_ranks = float(sum(like_ranks)) / float(len(like_ranks))

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

                print_help(ranks, 'RANKS CHOOSEN', username=request.user.username)

                mrr_score = mrr_at_k(ranks)
                print_help(mrr_score, 'MRR @ K', username=request.user.username)

                distinct_rank = list(dict.fromkeys([ rank for rank in ranks ]))
                print_help(distinct_rank, 'DISTINCT RANK', username=request.user.username)

                max_rank = max(distinct_rank)

                # binary_ndcg = [0] * TOTAL_WINDOW
                binary_ndcg = [0] * (max_rank + 1)

                for rank in distinct_rank:
                    binary_ndcg[rank] = 1

                print_help(binary_ndcg, 'BINARY NDCG', username=request.user.username)
                
                ndcg_score = ndcg_at_k(binary_ndcg, TOTAL_WINDOW, method = 1)
                print_help(ndcg_score, 'NDCG @ K', username=request.user.username)

                user_array.append([_id, mrr_score, ndcg_score, like_logs, like_ranks, avg_ranks])

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

def save_log(logs, filename='logs.txt'):
    dirname = os.path.dirname(__file__)
    up_two_levels = os.pardir + os.sep + os.pardir
    dest_path = os.path.join(dirname, up_two_levels, filename)
    with open(dest_path, 'a') as file:
        file.write(logs)

    file.close()

def mobile(request):
    """Return True if the request comes from a mobile device."""

    MOBILE_AGENT_RE=re.compile(r".*(iphone|mobile|androidtouch)",re.IGNORECASE)

    if MOBILE_AGENT_RE.match(request.META['HTTP_USER_AGENT']):
        return True
    
    return False


def train_als_model(user_id):
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

    if os.path.exists(dest_path):
        print_help(var='LOAD UCF MODEL', username='TRAIN ALS MODEL')

        ucf_model = load_model(dest_path)

    else:
        print_help(var='TRAINING UCF MODEL', username='TRAIN ALS MODEL')
        # Train UCF Model
        ucf_model = AlternatingLeastSquares(factors=64, regularization=0.05)
        ucf_model.fit(2 * user_product_matrix)

        dump_model(ucf_model, dest_path)

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


def train_model(request):
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

                        print_help(var='ALS AND APRIORI', username=request.user.username)
                        
                        # ALS METHOD
                        ALS_result = train_als_model(unique_user_obj.id)
                        
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
                        ALS_result = train_als_model(unique_user_obj.id)

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
