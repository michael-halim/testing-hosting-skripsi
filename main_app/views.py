from django.shortcuts import render,redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, PageNotAnInteger,EmptyPage
from django.utils.datastructures import MultiValueDictKeyError

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView,View
from django.http import JsonResponse
from django.db.models import Q, Max, Min

from .forms import CreateUserForm
from .decorators import unauthenticated_user
from .models import Item, Log, Like, Recommendation, User, ItemDetail, ExtendedRecommendation
from .helper import *

from zoneinfo import ZoneInfo
from random import randint, randrange
from operator import or_
from functools import reduce

import pandas as pd
import re

from cryptography.fernet import Fernet

def error_404_view(request, exception):
    """Handles Not Found Error"""
    # we add the path to the the 404.html file
    # here. The name of our HTML file is 404.html
    return render(request, '404.html')

def error_500_view(request):
    """Handles Server Error"""

    return render(request, '500.html')
    
class HomeView(LoginRequiredMixin, ListView):
    """Handles Home Page"""

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
        >>> local_tz = ZoneInfo('Asia/Bangkok')
        >>> db_tz = recommendations[0].created_at
        >>> print(db_tz.astimezone(local_tz)) # UTC+7 because Asia/Bangkok is UTC+7
        """

        print_help(var='TAKE RECOMMENDATION FROM DB', username=self.request.user.username)
        recommendations = ExtendedRecommendation.objects.filter(user_id = self.request.user.id).order_by('rank')
        
        # Get Recommended Product Ids
        recommended_product_ids = [ rec.product_id for rec in recommendations ]
        recommended_product_ids = recommended_product_ids[ : 6 * TOTAL_WINDOW ]

        print_help(var='BULK SELECT', username=self.request.user.username)

        # Select Item with Product Ids In Bulk
        recommendation_item = Item.objects.in_bulk(recommended_product_ids)

        # Select Recommended Item
        items = [ recommendation_item[product_id] for product_id in recommended_product_ids ]
        
        return items

class SearchView(LoginRequiredMixin, ListView):
    """Handle Searching"""

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

        #'if self.request.GET['something]' is called when it's empty, it will throw an error 
        # even when it's called in if statement

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
    """Handle Detail Pages"""

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
    """Handle About Pages"""

    login_url = '/login/'
    redirect_field_name = '/'
    
    def get(self,request):
        context = {}
        return render(request, 'main_app/about.html',context)

class FavoriteView(LoginRequiredMixin, View):
    """Handle Favorite Pages"""

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
    """Handle Copy Event"""
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

@login_required(login_url='main_app:home')
def categoryPage(request,category):
    """Handle Category Page"""
    print_help(var='ENTER CATEGORY PAGE VIEWS', username=request.user.username)
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
    """Handle Login Page"""
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
    """Handle Previous Page Event"""

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
    """Handle View Original Link Event"""
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
    """Handles Product Liked Event"""
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
    """Handle Question and Set Recommendation to DB"""

    is_show_score = True
    all_hybrid_recommendation, extended_recommendation = [], []
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
            
            extended_recommendation = create_random_recommendation(limit=Item.objects.filter(status=1).count())
            all_hybrid_recommendation = extended_recommendation[ :TOTAL_WINDOW ]

            print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION RANDOM', username=request.user.username)
            print_help(extended_recommendation, 'EXTENDED RECOMMENDATION RANDOM', username=request.user.username)

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

            extended_recommendation = create_random_recommendation(limit=Item.objects.filter(status=1).count())
            for rec in all_hybrid_recommendation:
                for co, other_rec in enumerate(extended_recommendation):
                    if rec[0] == other_rec[0]: 
                        extended_recommendation.pop(co)
                        break
            
            extended_recommendation = all_hybrid_recommendation + extended_recommendation
            print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION WITH QUESTION', username=request.user.username)

    else:      
        # If Choose Not to Answer the Question
        extended_recommendation = create_random_recommendation(limit=Item.objects.filter(status=1).count())
        all_hybrid_recommendation = extended_recommendation[ :TOTAL_WINDOW ]

        print_help(all_hybrid_recommendation, 'ALL HYBRID RECOMMENDATION RANDOM', username=request.user.username)
        print_help(extended_recommendation, 'EXTENDED RECOMMENDATION RANDOM', username=request.user.username)

    recommendation_object = Recommendation.objects.filter(user_id = request.user.id).order_by('rank')
    extended_recommendation_object = ExtendedRecommendation.objects.filter(user_id = request.user.id).order_by('rank')

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

        print_help(var='EXTENDED BULK CREATE', username=request.user.username)

        recommendations = []
        for count, item in enumerate(extended_recommendation, 1):
            _id = item
            if is_show_score:
                _id = item[0]
            
            recommendations.append(ExtendedRecommendation(user_id = request.user.id, 
                                                    product_id = _id, 
                                                    rank = count, 
                                                    created_at = now))

        print_help(var=recommendations, title='EXTENDED RECOMMENDATIONS', username=request.user.username)

        # Bulk Create Extended Recommendation
        ExtendedRecommendation.objects.bulk_create(recommendations)

    else:
        print_help(var='BULK UPDATE', username=request.user.username)

        # Zip QuerySet Recommendation and All Hybrid Recommendation and Then Enumerate from 1
        for count, (rec, item) in enumerate(zip(recommendation_object, all_hybrid_recommendation), 1):
            rec.product_id = item[0]
            rec.rank = count
            rec.created_at = now
        
        # Bulk Update Recommendation
        Recommendation.objects.bulk_update(recommendation_object, fields=['product_id','rank','created_at'])

        print_help(var='EXTENDED BULK UPDATE', username=request.user.username)
        # Zip QuerySet Recommendation and Extended Recommendation and Then Enumerate from 1
        for count, (rec, item) in enumerate(zip(extended_recommendation_object, extended_recommendation), 1):
            rec.product_id = item[0]
            rec.rank = count
            rec.created_at = now
        
        # Bulk Create Extended Recommendation
        ExtendedRecommendation.objects.bulk_update(extended_recommendation_object, fields=['product_id','rank','created_at'])

def create_random_recommendation(limit = TOTAL_WINDOW):
    """Return Random Recommendation
    >>> recsys = create_random_recommendations(limit=TOTAL_WINDOW)
    >>> print(recsys)
    [[item.id, 0.0]]
    """
    # Fetching All Item That Active
    random_recommendation = Item.objects.filter(status=1)
    # Give Score of 0 Because it is Random
    random_recommendation = [ [rec.id, 0.0] for rec in random_recommendation ]

    for i in range(len(random_recommendation)):
        random_number = randint(0, len(random_recommendation)-1)
        random_recommendation[i], random_recommendation[random_number] = \
            random_recommendation[random_number], random_recommendation[i]
    
    random_recommendation = random_recommendation[:limit]

    return random_recommendation

@login_required(login_url='main_app:home')
def ranking(request):
    """Logic to Ranking Page"""
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
                # print(logs.query)
                like_logs = Log.objects.filter(user_id= _id, event_type='LIKE', timestamp_in__range=[start_at, end_at])
                like_logs = [ log.product_id for log in like_logs ]
                like_logs = list(dict.fromkeys([ log for log in like_logs ]))

                like_ranks = []

                for item_id in like_logs:
                    recommended_item = ExtendedRecommendation.objects.filter(user_id=_id, product_id=item_id)
                    if len(recommended_item) <= 0:
                        like_ranks.append(int(TOTAL_WINDOW) + 1)
                    elif len(recommended_item) == 1:
                        like_ranks.append(recommended_item[0].rank)

                # print(sum(like_ranks))
                # print(len(like_ranks))
                avg_ranks = 0
                if not float(len(like_ranks)) == 0:
                    avg_ranks = float(sum(like_ranks)) / float(len(like_ranks))
                
                print_help(avg_ranks, 'AVG RANKS', username=request.user.username)

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

def mobile(request):
    """Return True if the request comes from a mobile device."""

    MOBILE_AGENT_RE=re.compile(r".*(iphone|mobile|androidtouch)",re.IGNORECASE)

    if MOBILE_AGENT_RE.match(request.META['HTTP_USER_AGENT']):
        return True

    return False
