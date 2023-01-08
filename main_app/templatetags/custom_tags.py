from django import template
from cryptography.fernet import Fernet
import re

register = template.Library()

def encrypt_id(value):
    key = b'gAAAAABjXkfW2XopKy1P1GCvCcMJM2zjsnGQP0DatJo='
    fernet = Fernet(key)
    value = str(value)
    return fernet.encrypt(value.encode('utf-8')).decode('utf-8')
    
def multiply(value, arg):
    return int(value) * (int(arg) - 1)

def add_current_rank(value, arg):
    return int(value) + int(arg)

def remove_substr(string, char):
    return string.replace(char,'')

def remove_substr_regex(string, options):
    regex, replace_with = options.split('%&')
    return re.sub(regex, replace_with, string)

register.filter('encrypt_id', encrypt_id)
register.filter('multiply', multiply)
register.filter('add_current_rank', add_current_rank)
register.filter('remove_substr', remove_substr)
register.filter('remove_substr_regex', remove_substr_regex)