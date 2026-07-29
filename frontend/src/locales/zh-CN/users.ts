// users 命名空间：UserList / UserGroupList 两页
export default {
  action: {
    saveAndContinue: '保存并继续',
  },
  role: {
    admin: '超级管理员',
    audit: '日志管理员',
    user: '普通用户',
    unknown: '未识别',
  },
  user: {
    title: '用户列表',
    subtitle: '管理平台注册用户 · 共 {total} 个 · 超级管理员 {admin} 个',
    add: '新增用户',
    searchPlaceholder: '搜索用户名 / 别名 / 邮箱',
    filterByGroup: '按组筛选',
    filterGroupLabel: '用户组',
    fromGroupTip: '来自用户组：{name}',
    clearFilter: '清除筛选',
    stats: {
      total: '共 {n} 个',
      admin: '超管',
      audit: '审计',
      normal: '普通',
    },
    col: {
      username: '用户名',
      alias: '别名',
      mail: '邮箱',
      group: '用户组',
      role: '角色',
      actions: '操作',
    },
    resetPwd: '重置密码',
    empty: {
      title: '暂无用户',
      hint: '点击右上角"新增用户"开始',
    },
    dialog: {
      add: '新增用户',
      edit: '编辑用户',
    },
    form: {
      username: '用户名',
      alias: '别名',
      mail: '邮箱',
      role: '角色',
      password: '密码',
      roleOption: {
        admin: '超级管理员 (admin)',
        audit: '日志管理员 (audit)',
        user: '普通用户 (user)',
      },
    },
    rules: {
      username: '请输入用户名',
      alias: '请输入别名',
    },
    pwdDialog: {
      title: '重置用户密码',
      username: '用户名',
      newPwd: '新密码',
      newPwdPlaceholder: '请输入新密码',
      adminPwd: '管理员密码',
      adminPwdPlaceholder: '请输入您自己的登录密码',
      sudoHint: '出于安全考虑，重置他人密码需输入您自己的登录密码进行二次确认',
      confirm: '确认重置',
      rules: {
        newPwdRequired: '请输入新密码',
        newPwdMin: '密码至少6位',
        adminPwdRequired: '请输入您自己的密码',
        adminPwdEmpty: '密码不能为空',
      },
      msg: {
        adminPwdNeeded: '请输入您自己的密码以确认操作',
        success: '密码重置成功',
        fail: '密码重置失败',
      },
    },
  },
  group: {
    title: '用户组',
    panelTitle: '用户组列表',
    subtitle: '管理用户分组 · 共 {total} 个组 · 成员总数 {members}',
    add: '新建组',
    searchPlaceholder: '搜索组名 / 备注',
    stats: {
      totalGroups: '共 {n} 个组',
      totalMembers: '总成员',
      avgPerGroup: '平均 {n} / 组',
    },
    col: {
      name: '组名',
      memberCount: '成员数',
      remarks: '备注',
      actions: '操作',
    },
    viewMembers: '查看 {n} 个成员',
    empty: {
      title: '暂无用户组',
      hint: '点击右上角"新建组"开始',
    },
    dialog: {
      add: '新建用户组',
      edit: '编辑用户组',
    },
    form: {
      name: '组名',
      nums: '用户数量',
      remarks: '备注',
    },
    rules: {
      name: '请输入组名',
    },
  },
}
