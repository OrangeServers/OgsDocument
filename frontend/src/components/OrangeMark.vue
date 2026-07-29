<!--
  OrangeMark · OrangeServer 品牌橘子图标
  直接复用品牌 logo（/juzi11.png，与登录页/侧栏同源），保证全站品牌一致。
  尺寸随容器 font-size（1em），思考动画（旋转/光晕）由使用方挂在
  .orange-mark 类与容器上，与本组件解耦。
-->
<template>
  <img
    class="orange-mark"
    src="/juzi11.png"
    alt=""
    aria-hidden="true"
    draggable="false"
  >
</template>

<style scoped>
.orange-mark {
  width: 1em;
  height: 1em;
  display: inline-block;
  object-fit: contain;
  user-select: none;
}
</style>
