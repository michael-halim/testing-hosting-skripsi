/**
* Execute a function given a delay time
* 
* @param {type} func
* @param {type} wait
* @param {type} immediate
* @returns {Function}
*/
var debounce = function (func, wait, immediate) {
     var timeout;
     return function() {
         var context = this, args = arguments;
         var later = function() {
                 timeout = null;
                 if (!immediate) func.apply(context, args);
         };
         var callNow = immediate && !timeout;
         clearTimeout(timeout);
         timeout = setTimeout(later, wait);
         if (callNow) func.apply(context, args);
     };
};

// var checkAlert = function(){
//     alert('check alert');
// }