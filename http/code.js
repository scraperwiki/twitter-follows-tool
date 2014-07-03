// Show very general purpose error
var something_went_wrong = function(content) {
    fix_button_texts()
    $('pre,.alert-error,.alert-warning,.help-inline').remove()
    var p = $('<p>').addClass('alert alert-error').html('<b>Something went wrong!</b> Click here to show technical details.').on('click', function() {
        $(this).next('pre').toggle()
    }).css('cursor', 'pointer')
    var pre = $('<pre>').html(content).hide()
    $('body').prepend(pre)
    $('body').prepend(p)
}

// Handle response from exec of twfollow.py
var done_exec_main = function(content, rename) {
    console.log(content)
    try {
        response = JSON.parse(content)

        // Handle various known responses
        if (response['status'] == 'auth-redirect') {
            scraperwiki.tool.redirect(response['url'])
            return
        }

        if (response['status'] == 'ok-updating') {
            // set another (full) run going in the background to start getting older tweets
            scraperwiki.exec('tool/twfollow.py >/dev/null 2>&1 &',
              function() {
              },
              function(obj, err, exception) {
                  something_went_wrong(err + "! " + exception)
              }
            )
        }

        // Show whatever we would on loading page
        // i.e. read status from database that twfollow.py set
        show_hide_stuff(null, rename)
    } catch(e) {
        // Otherwise an unknown error - e.g. an unexpected stack trace
        something_went_wrong(content)
        return
    }
}

// Unlimited followers
var allow_unlimited_followers = function(cb) {
   scraperwiki.user.profile(function(details) {
        var accountLevel = details.effective.accountLevel
        var allow = true
        if (accountLevel.match(/free/)) {
            allow = false
        }
        cb(allow)
   })
}

// Trigger to get unlimited followers
var get_them_all = function() {
   $(this).addClass('loading').html('Getting...').attr('disabled', true)
   $('pre,.alert-error,.alert-warning,.help-inline').remove()

   scraperwiki.exec("echo 10000000 > max_to_get.txt; ONETIME=1 tool/twfollow.py",
    function(content) {
        done_exec_main(content, false)
    },
    function(obj, err, exception) {
        something_went_wrong(err + "! " + exception) 
    }
   )
}

// Event function for when they click on the Go!, Refresh! or Reauthenticate buttons.
// Calls out to the Python script twfollow.py, which does the actual Twitter
// calling. 
var scrape_action = function() {
    $('pre,.alert-error,.alert-warning,.help-inline').remove()
    $('.control-group').removeClass('error')

    var q = $('#q').val()
    q = q.replace(/^@/,'')
    if (q.match(/[^a-zA-Z0-9_]/)) {
        $(".control-group").addClass('error')
        $(".controls").append('<span class="help-inline">Twitter user names only use the alphabet, numbers and _</span>')
        return
    }

    $(this).addClass('loading').html('Loading&hellip;').attr('disabled', true)

    var rename = false
    if ($(this).attr('id') == 'submit') {
      rename = true
    }

    // show_hide_stuff will check this variable later and contact intercom.io
    window.trackSearch = true

    // XXX temp
    fix_button_texts()
    var p = $('<p>').addClass('alert alert-error').html('<b>Twitter have suspended this tool!</b> We are working hard to get it back. Please <a href="https://blog.scraperwiki.com/2014/07/no-twitter-tools-for-now-months-refund/">read our blog post</a> for details.')
    $('body').prepend(p)
    return

    // Pass various OAuth bits of data to the Python script that is going to do the work
    scraperwiki.exec('echo ' + scraperwiki.shellEscape(q) + '>user.txt; ONETIME=1 tool/twfollow.py "' + callback_url + '" "' + oauth_verifier + '"', 
        function(content) {
            done_exec_main(content, rename)
        },
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception)
        }
    )
}

// Show rate limit and so on
var diagnostics_action = function() {
    var $link = $(this)
    if ($('#diagnostics-area .alert').is(":visible")) {
        $('#diagnostics-area .alert').slideUp(400)
        return
    }
    $link.next().show()

    // Pass various OAuth bits of data to the Python script that is going to do the work
    scraperwiki.exec('tool/twfollow.py diagnostics',
        function (content) {
            $link.next().hide()
            var diagnostics
        try {
            diagnostics = JSON.parse(content)
        } catch(e) {
            console.log("caught!!")
            // Otherwise an unknown error - e.g. an unexpected stack trace
            something_went_wrong(content)
            return
        }
        console.log(diagnostics)
        var html = ''
        if ('status' in diagnostics) {
            html += 'Status <b>' + diagnostics.status + '</b>. '
        }
        if ('user' in diagnostics) {
            html += 'Authenticated user is <b>@' + diagnostics.user + '</b>. '
            html += 'There are <b>' + diagnostics.followers_remaining + '/' + diagnostics.followers_limit + '</b> followers API calls left '
            html += 'resetting <b>' + moment.unix(diagnostics.users_reset).fromNow() + "</b>, "
            html += '<b>' + diagnostics.friends_remaining + '/' + diagnostics.friends_limit + '</b> following API calls left '
            html += 'resetting <b>' + moment.unix(diagnostics.users_reset).fromNow() + "</b>, "
            html += '<b>' + diagnostics.users_remaining + '/' + diagnostics.users_limit + '</b> user details API calls left '
            html += 'resetting <b>' + moment.unix(diagnostics.users_reset).fromNow() + "</b>. "
        }
        if (!('crontab' in diagnostics)) {
            html += 'Not scheduled. '
        } else if (diagnostics.crontab.match(/no crontab/)) {
            html += 'Not scheduled. '
        } else {
            html += 'Scheduled to update at <b>' + parseInt(diagnostics.crontab) + ' minutes</b> past the hour. '
        }
        $('#diagnostics-area .alert').html(html).slideDown(400)
    },
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception)
        }
    )
}

// Clear data and start again
var clear_action = function() {
    $(this).addClass('loading').html('Clearing&hellip;').attr('disabled', true)
    $('pre,.alert-error,.alert-warning,.help-inline').remove()

    scraperwiki.dataset.name("Get Twitter friends")

    scraperwiki.reporting.user({increments: {tf_resets: 1}})

    scraperwiki.exec("tool/twfollow.py clean-slate",
        function(content) {
            done_exec_main(content, false)
        },
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception) 
        }
    )
}

// Buttons show "Loading..." and so on while working. This puts all their text back after.
var fix_button_texts = function() {
    $('#reauthenticate').removeClass('loading').html('Reauthenticate').attr('disabled', false)
    $('#submit').removeClass('loading').html('Go').attr('disabled', false)
    $('#clear-data').removeClass('loading').html('Monitor someone else*').attr('disabled', false)
}

var track_search_if_required = function() {
    if(window.trackSearch) {
        scraperwiki.reporting.user({increments: {tf_searches: 1}})
        window.trackSearch = undefined
    }
}
 
// Show the right form (get settings, or the refresh data one)
var show_hide_stuff = function(done, rename) {
    // Find out what user it is
    scraperwiki.exec('touch user.txt; cat user.txt', function(data) {
        data = $.trim(data)
        $('#q').val(data)
        $('.who').text(data)

        if (rename) {   
            scraperwiki.dataset.name("Twitter friends of @" + data)
        }

    // Show expected delivery time
    scraperwiki.sql('select sum(batch_got) as got, sum(batch_expected) as expected from __status', function(results){
	var got = results[0]['got']
	var expected = results[0]['expected']
	$('.batch_got').text(got)
	$('.batch_expected').text(expected)
	
	var tweets_per_request = 5000
	var request_per_hour = 3 
	var hours_left = Math.round((expected - got) / request_per_hour / tweets_per_request)
	var days_left = Math.round(hours_left / 24)
	if (hours_left <= 1) {
	    eta = "1 hour"
	} else if (hours_left < 13) {
	    eta = hours_left + " hours"
	} else if (days_left < 2) {
	    eta = "1 day"
	} else {
	    eta = days_left + " days"
	}
	$('#eta').text(eta)
        }
    )

        // Show right form
        scraperwiki.sql('select * from __status where id = "global"', function(results){
            results = results[0]

            // results['batch_expected'] += 1; // debugging, force a state

            console.log(results)

            $('.settings').hide()
            fix_button_texts()
            $('.done_when').text(moment(results['when']).format("Do MMM YYYY"))
	    // we run @hourly in cron, and until Twitter stops us, which happens with
	    // users/lookup rate limit (18000 in 15 min window, so three chunks of 5000)

            $('pre,.alert-error,.alert-warning,.help-inline').remove()
            $('.control-group').removeClass('error')

            if (results['current_status'] == 'auth-redirect') {
                $('#settings-auth').show()
                $('#settings-clear').show()
                // if during auth, click it
                if (oauth_verifier) {
                    $("#reauthenticate").trigger("click")
                    scraperwiki.dataset.name("Twitter friends of @" + data)
                }
            } else if (results['current_status'] == 'not-there') {
                $('#settings-get').show()
                var p = $('<p>').addClass('alert alert-error').html("<b>User not found on Twitter!</b> Check the spelling and that they have an account and try again.")
                $('body').prepend(p)
            } else if (results['current_status'] == 'rate-limit') {
                $('#settings-working').show()
                var p = $('<p>').addClass('alert alert-warning').html('<b>Twitter has asked us to slow down!</b> See the <a href="https://scraperwiki.com/help/twitter-faq">FAQ</a> for details and suggestions.')
                $('body').prepend(p)
                $('#settings-clear').show()
            } else if (results['current_status'] == 'ok-updating') {
                $('#settings-working').show()
                $('#settings-clear').show()
                track_search_if_required()
            } else if (results['current_status'] == 'ok-done') {
                $('#settings-done').show()
                $('#settings-clear').show()
                track_search_if_required()
            } else if (results['current_status'] == 'ok-limit') {
                allow_unlimited_followers(function(allow) {
                  if (allow) {
                    $('#error-too-many').hide()
                    $('#allow-too-many').show()
                  } else {
                    $('#error-too-many').show()
                    $('#allow-too-many').hide()
                  }
                  $('#settings-limit').show()
                  $('#settings-clear').show()
                  track_search_if_required()
                })
            } else if (results['current_status'] == 'clean-slate') {
                $('#settings-get').show()
            } else {
                alert("Unknown internal state: " + results['current_status'])
            }
            if (done) {
                done()
            }
        }, function(results) {
            // this is bad as it will masks real errors - we have to show the form as
            // no SQLite database gives an error
            fix_button_texts()
            $('#settings-get').show()
            if (done) {
                done()
            }
        })
    }, function(obj, err, exception) {
       something_went_wrong(err + "! " + exception)
    })
}

// Get OAuth parameters that we need from the URL
var settings = scraperwiki.readSettings()
var callback_url
var oauth_verifier
scraperwiki.tool.getURL(function(our_url) {
    console.log(our_url)
    var url = $.url(our_url)
    oauth_verifier = url.param('oauth_verifier')
    // remove query parameters for the callback URL, so they don't stack up if we
    // go multiple times to Twitter 
    callback_url = url.attr('base') + url.attr('path')
    // only when we have the callback URL, allow the submit button to be clicked
    $("#submit,#reauthenticate,#clear-data").removeAttr("disabled")
})

$(document).ready(function() {
    show_hide_stuff()

    $('#q').on('keypress', function(e){
      if(e.which == 13){
        $('#submit').trigger('click')
      }
    })

    $('#clear-data').on('click', clear_action)
    $('#submit,#reauthenticate').on('click', scrape_action)
    $('#diagnostics').on('click', diagnostics_action)
    $('#get-them-all').on('click', get_them_all)
})



