$(function () {
  $('body').on('click', 'label.signup', function () {
    $('form.login').css({
      'margin-left': '-50%',
    });
    $('.title-text.login').css({
      'margin-left': '-50%',
    });
  });
  $('body').on('click', 'label.login', function () {
    $('form.login').css({
      'margin-left': '0%',
    });
    $('.title-text.login').css({
      'margin-left': '0%',
    });
  });
  $('body').on('click', 'form .signup-link a', function () {
    $('form.login').css({
      'margin-left': '-50%',
    });
    $('.title-text.login').css({
      'margin-left': '-50%',
    });
    return false;
  });
});
