(function (win, $) {
  'use strict';

  $.namespace('win.booktype.editor.settings');

  win.booktype.editor.settings = (function () {

    var SettingsRouter = Backbone.Router.extend({
      routes: {
        'settings': 'settings',
        'settings/:module': 'loadSetting'
      },

      settings: function () {
        var activePanel = win.booktype.editor.getActivePanel();

        activePanel.hide(function () {
          win.booktype.editor.data.activePanel = win.booktype.editor.data.panels['settings'];
          win.booktype.editor.data.activePanel.show();
        });
      },

      loadSetting: function (module) {
        if (win.booktype.editor.settings.uiLoaded === undefined) {
          this.settings();
        }

        // TODO: check if module is valid

        // check if base content has been loaded

        // load corresponding module
        var params = {
          'setting': module,
          'bookid': win.booktype.currentBookID
        };

        win.booktype.ui.notify('Loading section');

        $.get(win.booktype.bookSettingsURL + '?' + $.param(params),
          function (html) {
            $('#setting_content').html(html);
          }).error(function () {
            var notAvailable = win.booktype.ui.getTemplate('templateModuleNotAvailable');
            $('#setting_content').html(notAvailable);
          }).complete(function () {
            win.booktype.ui.notify();
          }
        );
      }
    });

    var router = new SettingsRouter();

    var _show = function () {
      $('#button-settings').addClass('active');

      var header = win.booktype.ui.getTemplate('templateSettingsHeader');
      $('DIV.contentHeader').html(header);

      var t = win.booktype.ui.getTemplate('templateSettingsContent');
      $('#content').html(t).addClass('settings');

      win.booktype.editor.settings.uiLoaded = true;
    };

    var _hide = function (callback) {
      $('#button-settings').removeClass('active');

      // Destroy tooltip
      $('DIV.contentHeader [rel=tooltip]').tooltip('destroy');

      // Clear content
      $('#content').empty();
      $('DIV.contentHeader').empty();

      if (!_.isUndefined(callback)) {
        callback();
      }
    };

    var _init = function () {
      $('#button-settings').on('click', function () { Backbone.history.navigate('settings', true); });

      $(document).on('shown.bs.tab', 'a[data-toggle="tab"]', function (e) {
        // trigger url via backbone router
        var option = $(e.target).attr('href').replace('#', '');
        router.navigate('settings/' + option, { trigger: true });
        return false;
      });

      $(document).on('click', '#saveBookSettings', function () {
        var $form = $(this).closest('form');
        var flashMessage = null;

        win.booktype.ui.notify(win.booktype._('loading_data', 'Loading data.'));
        $.ajax({
          type: 'POST',
          url: $form.attr('action'),
          data: $form.serialize(),
          success: function (resp) {
            if (resp.error) {
              if (resp.data !== undefined) {
                $('#setting_content').empty().html(resp.data);
              } else {
                flashMessage = createFlash(resp.message, 'warning');
              }
            } else {
              Backbone.history.navigate('settings', true);
              flashMessage = createFlash(resp.message, 'success');
            }
            win.booktype.ui.notify();
            $('#setting_content').before(flashMessage);
            dismissFlash();
          }
        });

        return false;
      });

      // Set a new license Link, when license combobox setting changes
      $(document).on('change', 'SELECT[name=license]', function () {
        var licenseId = $(this).val();
        var licenseList = window.booktype.licenseList;

        if (licenseId in licenseList) {
          $('#license-link').attr('href', licenseList[licenseId]);
        }
      });

      // ----- Roles -----
      $(document).on('mouseenter', '.roles .list li', function () {
        $(this).addClass('show-remove-btn');
      });

      $(document).on('mouseleave', '.roles .list li', function () {
        $(this).removeClass('show-remove-btn');
      });

      // toggle description show and hide
      $(document).on('click', '.toggle-description a', function () {
        $(this).closest('.box').find('.role-description').toggleClass('show');
      });

      // click on a user activates options
      $(document).on('click', '#assignUsers .users-list .list li', function () {
        $(this).parent().children().removeClass('active');
        $(this).toggleClass('active');

        var username = $(this).find('p').html(),
          userRoles = $(this).data('user-roles'),
          roles = $(this).closest('.modal-body').find('.assign-options .roles-options button');

        $(this).closest('.modal-body').find('.assign-options .user-roles span').empty().append(username);

        // reset roles buttons
        $(roles).removeClass('btn-success disabled-tooltip active');
        $(roles).addClass('btn-default');

        // for each role, check if already enable for that user
        $.each(roles, function (_i, role) {
          // remove tooltip for disabled buttons
          unWrapDisabledRole(role);

          var roleId = parseInt($(role).data('role-id'), 10);
          if ($.inArray(roleId, userRoles) === -1) {
            $(role).removeClass('disabled');
          } else {
            $(role)
              .removeClass('btn-default')
              .addClass('disabled-tooltip btn-success disabled');

            wrapDisabledRole(role);
            enableModalTooltips();
          }
        });
      });

      $(document).on('click', '.assign-options .roles-options .btn', function () {
        $(this).closest('.modal-content').find('#assign').removeClass('disabled');
      });

      // reset everything on modal hide
      $(document).on('hidden.bs.modal', '#assignUsers', function () {
        $('.users-list .list li').removeClass('active');
        $('.assign-options .roles-options button').addClass('disabled').removeClass('active');
        $('.assign-options .user-roles span').empty();
        $('#assign').addClass('disabled');
      });

      // calculate the height and apply to user list
      $(document).on('shown.bs.modal', '#assignUsers', function () {
        var optionsHeight = $(this).find('.assign-options').outerHeight();
        $(this).find('.users-list').css('bottom', optionsHeight);

        enableModalTooltips();
      });

      // patching for caise insensitive on jquery contains
      $.expr[':'].contains = $.expr.createPseudo(function (arg) {
        return function (elem) {
          return $(elem).text().toUpperCase().indexOf(arg.toUpperCase()) >= 0;
        };
      });

      // we need an inline search for user in assign roles
      $(document).on('keyup', '.search-box input', function () {
        var value = $(this).val();

        $('.users-list > ul > li:not(:contains(' + value + '))').hide();
        $('.users-list > ul > li:contains(' + value + ')').show();
      });

      $(document).on('click', '.search-box .btn', function () {
        $('.search-box input').trigger('keyup');
      });

      // assign user to role
      $(document).on('click', '#assign', function () {
        win.booktype.ui.notify(win.booktype._('sending_data', 'Sending data.'));
        var user = $('.users-list > ul > li.active:first').data('user-id'),
          roles = $('.role-btn.active').not('.disabled');

        var rolesid = $.map(roles, function (elem) {
          var roleID = $(elem).data('role-id');
          if (typeof roleID === 'number') {
            return roleID;
          }
        });

        win.booktype.sendToCurrentBook({
          'command': 'assign_to_role',
          'userid': user,
          'roles': rolesid
        },
          function () {
            win.booktype.ui.notify();
            $('#assignUsers').modal('hide');
            Backbone.history.loadUrl('settings/roles');
          }
        );
      });

      // remove user from role
      $(document).on('click', '.remove-btn button', function () {
        var self = this,
          userID = $(this).data('user-id'),
          bookRoleID = $(this).data('bookrole-id'),
          roleID = $(this).data('role-id');


        win.booktype.ui.notify(win.booktype._('sending_data', 'Sending data.'));

        win.booktype.sendToCurrentBook({
          'command': 'remove_user_from_role',
          'userid': userID,
          'roleid': bookRoleID
        },
          function (data) {
            win.booktype.ui.notify();
            if (data.result) {
              $(self).closest('li').remove();
              var userToAssign = $('#assignUsers ul li[data-user-id="' + userID + '"]');
              var newRolesIDS = userToAssign.data('user-roles').filter(function (id) {return id !== roleID;});
              console.log(newRolesIDS, roleID);
              userToAssign.data('user-roles', newRolesIDS);
            } else {
              win.booktype.ui.notify(win.booktype._('sending_data'));
            }
          }
        );
      });

    };

    var createFlash = function (message, alert) {
      var flashTempl = _.template(
        $('script.templateFlashMessage').html()
      );
      return flashTempl({'message': message, 'alert_type': alert});
    };

    var dismissFlash = function () {
      // fade out all alerts with bk-dismiss class.
      $('.bk-dismiss').each(function (i, alert) {
        var timeout = $(alert).data('dismiss-secs');
        setTimeout(function () {
          $(alert)
            .fadeOut(1000, 'linear')
            .remove();
        }, parseInt(timeout, 10) * 1000);
      });
    };

    var enableModalTooltips = function () {
      $('[rel=tooltip]').tooltip({
        container: 'body'
      });
    };

    var wrapDisabledRole = function (roleBtn) {
      var tooltip = win.booktype._('already_in_role', 'Selected user already belongs to this role');
      $(roleBtn).wrap(function () {
        return '<div rel="tooltip" style="display: inline-block" data-placement="top" data-original-title="' + tooltip + '"></div>';
      });
    };

    var unWrapDisabledRole = function (roleBtn) {
      if ($(roleBtn).parent().is('div[rel=tooltip]')) {
        $(roleBtn).unwrap();
      }
    };

    return {
      'init': _init,
      'show': _show,
      'hide': _hide,
      'router': router,
      'name': 'settings',
    };
  })();

})(window, jQuery);