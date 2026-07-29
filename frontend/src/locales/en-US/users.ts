import type zh from '../zh-CN/users'

export default {
  action: {
    saveAndContinue: 'Save & add another',
  },
  role: {
    admin: 'Super admin',
    audit: 'Audit admin',
    user: 'Regular user',
    unknown: 'Unknown',
  },
  user: {
    title: 'Users',
    subtitle: 'Manage platform users · {total} total · {admin} super admin(s)',
    add: 'Add user',
    searchPlaceholder: 'Search username / alias / email',
    filterByGroup: 'Filter by group',
    filterGroupLabel: 'User group',
    fromGroupTip: 'From user group: {name}',
    clearFilter: 'Clear filter',
    stats: {
      total: '{n} total',
      admin: 'Admin',
      audit: 'Audit',
      normal: 'Regular',
    },
    col: {
      username: 'Username',
      alias: 'Alias',
      mail: 'Email',
      group: 'User group',
      role: 'Role',
      actions: 'Actions',
    },
    resetPwd: 'Reset password',
    empty: {
      title: 'No users yet',
      hint: 'Click "Add user" in the top right to get started',
    },
    dialog: {
      add: 'Add user',
      edit: 'Edit user',
    },
    form: {
      username: 'Username',
      alias: 'Alias',
      mail: 'Email',
      role: 'Role',
      password: 'Password',
      roleOption: {
        admin: 'Super admin (admin)',
        audit: 'Audit admin (audit)',
        user: 'Regular user (user)',
      },
    },
    rules: {
      username: 'Username is required',
      alias: 'Alias is required',
    },
    pwdDialog: {
      title: 'Reset user password',
      username: 'Username',
      newPwd: 'New password',
      newPwdPlaceholder: 'Enter new password',
      adminPwd: 'Your password',
      adminPwdPlaceholder: 'Enter your own login password',
      sudoHint: 'For security, resetting another user\'s password requires confirming with your own login password',
      confirm: 'Confirm reset',
      rules: {
        newPwdRequired: 'New password is required',
        newPwdMin: 'At least 6 characters',
        adminPwdRequired: 'Your own password is required',
        adminPwdEmpty: 'Password cannot be empty',
      },
      msg: {
        adminPwdNeeded: 'Enter your own password to confirm this action',
        success: 'Password reset successfully',
        fail: 'Password reset failed',
      },
    },
  },
  group: {
    title: 'User groups',
    panelTitle: 'User group list',
    subtitle: 'Manage user groups · {total} groups · {members} members',
    add: 'New group',
    searchPlaceholder: 'Search group name / remarks',
    stats: {
      totalGroups: '{n} groups',
      totalMembers: 'Members',
      avgPerGroup: 'Avg {n} / group',
    },
    col: {
      name: 'Group',
      memberCount: 'Members',
      remarks: 'Remarks',
      actions: 'Actions',
    },
    viewMembers: 'View {n} member(s)',
    empty: {
      title: 'No user groups yet',
      hint: 'Click "New group" in the top right to get started',
    },
    dialog: {
      add: 'New user group',
      edit: 'Edit user group',
    },
    form: {
      name: 'Group name',
      nums: 'User count',
      remarks: 'Remarks',
    },
    rules: {
      name: 'Group name is required',
    },
  },
} satisfies typeof zh
