window.chan = new QWebChannel(qt.webChannelTransport, function(channel) {
    let API = channel.objects.VIntelAPI;

    let ALARM_COLORS = [
        [60*4,     '#FF0000', '#FFFFFF'],
        [60*10,    '#FF9B0F', '#FFFFFF'],
        [60*15,    '#FFFA0F', '#000000'],
        [60*25,    '#FFFDA2', '#000000'],
        [60*60*24, '#FFFFFF', '#000000']
    ];

    let SECONDS_UNTIL_WHITE = 10*60;

    let formatTime = function (min, sec) {
        let str1 = new String(min);
        let str2 = new String(sec);

        if (str1.length == 1) {
            str1 = '0' + str1;
        }

        if (str2.length == 1) {
            str2 = '0' + str2;
        }

        return str1 + ':' + str2;
    };

    let updateSystem = function ($elm, now) {
        let sysid = $elm.attr('id').match(/\d+/)[0];
        let $text = $elm.find('.st, .er').first();
        //let $text = $elm.find('#txt' + sysid).first();
        //$text.addClass('stopwatch');
        let last_state = $elm.attr('data-last-status');

        if (last_state == undefined) return;

        let time_alarm = parseInt($elm.attr('data-last-alarm'));
        if (isNaN(time_alarm)) time_alarm = now;

        let timediff = now - time_alarm;
        let bg_color = '';
        let fill_color = '';
        let seconds = timediff % 60;
        let minutes = Math.round((timediff - seconds) / 60);
        let string  = formatTime(minutes, seconds);
        let stopTimer = false;

        if (last_state == 'alarm') {
            let i=0;
            for (i=0; i<ALARM_COLORS.length; i++) {
                if (timediff <= ALARM_COLORS[i][0]) break;
            }

            if (i == ALARM_COLORS.length - 1) stopTimer = true;

            bg_color   = ALARM_COLORS[i][1];
            fill_color = ALARM_COLORS[i][2];
        } else if (last_state == 'clear') {
            string = 'clr: ' + string;

            if (timediff > SECONDS_UNTIL_WHITE) stopTimer = true;

            let color_main = 255;
            let color_alt  = Math.round(timediff / (SECONDS_UNTIL_WHITE / 255.0));
            if (color_alt > 255) {
                color_alt = 255;
                fill_color = '#008100';
            } else {
                fill_color = '#000000';
            }

            bg_color = 'rgb(' + color_alt + ',' + color_main + ',' + color_alt +')';
        } else if (last_state == 'request') {
        } else {
            window.console.log('unknown status "'+last_state+'"');
        }

        if (stopTimer) {
            $text.removeAttr('style');
            $text.text('?');
            $elm.find('a rect').removeAttr('style');

            console.log('disabled timer for system ' + $elm.find('.ss, .es').first().text());
            $elm.removeClass('stopwatch');
        } else {
            $text.attr('style', 'fill: '+fill_color);
            $text.text(string);
            $elm.find('a rect').attr('style', 'fill: ' + bg_color);
        }
    };

    let markerTimeout;
    let startMarker = function ($obj) {
        let first = $obj.attr('activated');

        markerTimeout = window.setInterval(function () {
            let now = new Date();
            now = now.getTime();

            let new_value = 1 - (now - first) / 3000;

            if (new_value < 0) new_value = 0;

            $obj.attr('opacity', new_value);

            if (new_value == 0) {
                window.clearInterval(markerTimeout);
            }
        }, 50);
    };

    let last_watch_count = 0;
    window.setInterval(function () {
        let now_d = new Date();
        let now = parseInt(now_d.getTime() / 1000);

        let arr = $('.stopwatch');
        //*
        if (last_watch_count != arr.length) {
            last_watch_count = arr.length;
            window.console.log('stopwatch x'+arr.length);
        }
        //*/

        arr.each(function () { updateSystem($(this), now) });
    }, 1000);

    API.js_message.connect(function (str) {
        let obj = JSON.parse(str);
        let now_d = new Date();
        let now = Math.round(now_d.getTime() / 1000);

        if (obj.type == 'load_svg') {
            document.getElementById('svg_container').innerHTML = obj.data;
        } else if (obj.type == 'set_style') {
            let $elm = $('#map_style');
            if ($elm.length == 0) {
                window.console.log('creating style element');
                $elm = $(document.createElement('style'));
                $elm.attr('type', 'text/css');
                $elm.attr('id', 'map_style');
                $('head').append($elm);
            } else {
                window.console.log('found style element');
            }

            //window.console.log('style: ' + obj.style);

            $elm.html(obj.style);
        } else if (obj.type == 'status_change') {
            if (obj.status == 'alarm' || obj.status == 'clear') {
                window.console.log('status change: system ' + obj.sysname + ' ' + obj.status);

                let $elm = $('#def' + obj.sysid);
                if ($elm.length > 0) {
                    $elm.attr('data-last-alarm', now);
                    $elm.attr('data-last-status', obj.status);

                    $elm.addClass('stopwatch');

                    updateSystem($elm, now);
                } else {
                    window.alert('System #'+obj.sysid+' not found on map');
                }
            } else {
                window.console.log('status change: system ' + obj.sysname + ' ' + obj.status + ' -- ignoring');
            }
        } else if (obj.type == 'mark_system') {
            let $sys = $('[data-systemname="'+obj.sysname+'"]');
            if ($sys.length == 1) {
                let sysid = $sys.attr('data-systemid');
                let $obj  = $('#sys'+sysid);
                let $mark = $('#select_marker');

                let x = Math.round(parseFloat($obj.attr('x')) + parseFloat($obj.attr('width'))  / 2);
                let y = Math.round(parseFloat($obj.attr('y')) + parseFloat($obj.attr('height')) / 2);

                //window.console.log('found "'+obj.sysname+'" system #' + sysid + ' at ' + x + 'x' + y);

                $mark.attr('transform', 'translate('+x+', '+y+')');
                $mark.attr('opacity', '1');
                $mark.attr('activated', now_d.getTime());

                startMarker($mark);
            } else if ($sys.length > 1) {
                window.console.log('found "'+obj.sysname+'" too many systems: ' + $sys.length);
            } else {
                window.console.log('system "'+obj.sysname+'" not found');
            }
        } else if (obj.type == 'mark_player') {
            window.console.log('mark player "'+obj.name+'" @ ' + obj.sysname);

            let $obj  = $('[data-systemname="'+obj.sysname+'"]');
            let $sys;
            if ($obj.length == 1) {
                $sys = $('#sys'+$obj.attr('data-systemid'));
            }

            let $jmp = $('#jumps');
            if ($jmp.length == 1) {
                let $mark = $jmp.find('.player_mark').filter(function () { return $(this).attr('data-player-name') == obj.name });

                if (!$sys) {
                    window.console.log('system "'+obj.sysname+'" not found');
                    if ($mark.length == 1) $mark.remove();
                } else {
                    let newMark = false;
                    if ($mark.length == 0) {
                        //window.console.log('mark  "'+obj.name+'" not found, creating new');

                        $mark = $(document.createElementNS('http://www.w3.org/2000/svg', 'ellipse'));

                        //$mark = $('<ellipse/>');
                        $mark.addClass('player_mark');
                        $mark.attr('data-player-name', obj.name);
                        $mark.attr('style', 'fill:#8b008d');

                        $mark.prependTo($jmp);

                        newMark = true;
                    }

                    let sys_x = parseFloat($sys.attr('x')),
                        sys_y = parseFloat($sys.attr('y')),
                        sys_w = parseFloat($sys.attr('width')),
                        sys_h = parseFloat($sys.attr('height'));

                    //window.console.log('sys_x='+sys_x+' sys_y='+sys_y+' sys_w='+sys_w+' sys_h='+sys_h);

                    let center_x = sys_x + sys_w / 2;
                    let center_y = sys_y + sys_h / 2;

                    $mark.attr('cx', Math.round(center_x - 2.5));
                    $mark.attr('cy', Math.round(center_y));

                    $mark.attr('rx', Math.round(sys_w / 2) + 4);
                    $mark.attr('ry', Math.round(sys_h / 2) + 4);
                }
            } else {
                window.console.log('#jumps node not found, length=' + $jmp.length);
            }
        } else {
            window.console.log(obj.type, obj);
        }
        //window.alert('page input '+str);
        //window.console.log(str);
    });

    API.bridge_ready();

    //API.from_page('page output');
    API.from_page(JSON.stringify({ type: 'test', testkey : 'testvalue' }));
    window.alert('init done');

    $(document).on('click', 'use', function (e) {
        //window.alert('click!');
        let $use = $(this);
        let $sym = $('#def' + $use.attr('id').match(/\d+/)[0]);
        let $a   = $sym.find('a').first();

        API.from_page(JSON.stringify({
             type: 'click',
             sys_id   : $sym.attr('id'),
             sys_name : $a.attr('data-systemname'),
             sys_href : $a.attr('xlink:href')
        }));
    })
});