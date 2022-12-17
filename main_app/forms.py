from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms  
from django.core.exceptions import ValidationError  
from django.forms.fields import EmailField  
from django.forms.forms import Form  

class CreateUserForm(UserCreationForm):
    username = forms.CharField(label='username', min_length=5, max_length=150)  
    email = forms.EmailField(label='email')  
    password1 = forms.CharField(label='password', widget=forms.PasswordInput)  
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)  

    def clean_username(self):  
        username = self.cleaned_data['username'].lower()  
        new = User.objects.filter(username = username)  
        
        if new.count():  
            raise ValidationError("User Already Exist")  
        
        return username  
  
    def clean_email(self):  
        email = self.cleaned_data['email'].lower()  
        new = User.objects.filter(email=email)  

        if new.count():  
            raise ValidationError(" Email Already Exist")  

        return email  
  
    def clean_password2(self):  
        password1 = self.cleaned_data['password1']  
        password2 = self.cleaned_data['password2']  

        if password1 and password2 and password1 != password2:  
            raise ValidationError("Password don't match")  

        return password2  

    class Meta:
        model = User
        fields = ['username','email','password1','password2']

    def __init__(self, *args, **kwargs):
        super(UserCreationForm, self).__init__(*args, **kwargs)

        self.fields['username'].widget.attrs = {'autofocus': False, 'placeholder':'Username'}
        self.fields['email'].widget.attrs = {'autofocus': False, 'placeholder':'Email'}
        self.fields['password1'].widget.attrs = {'autofocus': False, 'placeholder':'Password'}
        self.fields['password2'].widget.attrs = {'autofocus': False, 'placeholder':'Confirm Password'}