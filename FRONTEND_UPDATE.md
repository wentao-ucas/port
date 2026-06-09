# 前端更新说明 - Frontend Update Guide

## 需要更新的内容

由于前端App.vue文件较大（750行），以下是需要修改的关键部分。可以根据这些说明手动修改，或者使用提供的脚本自动替换。

---

## 1. 修改生成记录页面 - 改为日期范围选择

### 位置：第125-145行左右（el-tab-pane name="generate"）

### 原代码：
```vue
<el-form-item label="年份">
  <el-input-number v-model="generateForm.year" :min="2020" :max="2030" />
</el-form-item>

<el-form-item label="月份">
  <el-input-number v-model="generateForm.month" :min="1" :max="12" />
</el-form-item>

<el-form-item label="正常工时">
  <el-input-number v-model="generateForm.normal_hours" :min="0" :max="24" :step="0.5" />
  <span style="margin-left: 10px; color: #909399;">每天的正常工作时长</span>
</el-form-item>

<el-form-item label="加班工时">
  <el-input-number v-model="generateForm.overtime_hours" :min="0" :max="24" :step="0.5" />
  <span style="margin-left: 10px; color: #909399;">每天的加班时长</span>
</el-form-item>
```

### 新代码：
```vue
<el-form-item label="开始日期">
  <el-date-picker 
    v-model="generateForm.start_date" 
    type="date"
    value-format="YYYY-MM-DD"
    placeholder="选择开始日期"
  />
</el-form-item>

<el-form-item label="结束日期">
  <el-date-picker 
    v-model="generateForm.end_date" 
    type="date"
    value-format="YYYY-MM-DD"
    placeholder="选择结束日期"
  />
</el-form-item>
```

### 说明文本也要修改：
```vue
<el-alert
  title="💡 说明"
  type="info"
  :closable="false"
  style="margin-bottom: 20px"
>
  选择日期范围，系统会自动查询实际可报工时并生成工作日记录（自动排除周末）
</el-alert>
```

---

## 2. 修改JS数据定义

### 位置：<script setup> 部分（约第380-390行）

### 原代码：
```js
const generateForm = ref({
  year: new Date().getFullYear(),
  month: new Date().getMonth() + 1,
  normal_hours: 8.0,
  overtime_hours: 0.0
})
```

### 新代码：
```js
const generateForm = ref({
  start_date: '',
  end_date: ''
})
```

---

## 3. 修改生成记录方法

### 位置：<script setup> 部分（约第520-550行）

### 原代码（需要删除日期计算逻辑）：
```js
const generateRecords = async () => {
  try {
    loading.value = true
    
    // 原来的逻辑：计算year和month
    // 需要删除这部分
    
    const res = await axios.post('/api/generate', {
      year: generateForm.value.year,
      month: generateForm.value.month,
      normal_hours: generateForm.value.normal_hours,
      overtime_hours: generateForm.value.overtime_hours
    })
    // ...
  }
}
```

### 新代码：
```js
const generateRecords = async () => {
  if (!generateForm.value.start_date || !generateForm.value.end_date) {
    ElMessage.warning('请选择日期范围')
    return
  }
  
  try {
    loading.value = true
    const res = await axios.post('/api/generate', {
      start_date: generateForm.value.start_date,
      end_date: generateForm.value.end_date
    })
    if (res.data.success) {
      ElMessage.success(res.data.message)
      // 切换到记录管理并刷新
      activeTab.value = 'records'
      await loadRecords()
    } else {
      ElMessage.error(res.data.message)
    }
  } catch (error) {
    ElMessage.error('生成失败: ' + error.message)
  } finally {
    loading.value = false
  }
}
```

---

## 4. 添加Excel导入导出按钮

### 位置：报工管理页面的header部分（约第245行）

### 在刷新按钮后面添加：
```vue
<el-button type="success" @click="exportExcel">
  <el-icon style="margin-right: 5px;"><Download /></el-icon>
  导出Excel
</el-button>
<el-upload
  action="/api/excel/import"
  :headers="{ 'X-Username': 'default_user' }"
  :show-file-list="false"
  :on-success="handleImportSuccess"
  :on-error="handleImportError"
  accept=".xlsx,.xls"
  style="display: inline-block; margin-left: 10px;"
>
  <el-button type="warning">
    <el-icon style="margin-right: 5px;"><Upload /></el-icon>
    导入Excel
  </el-button>
</el-upload>
```

### 添加对应的方法（约第680行）：
```js
// Excel导出
const exportExcel = () => {
  const username = 'default_user'  // 可以改为动态获取
  window.open(`/api/excel/export?username=${username}`, '_blank')
}

// Excel导入成功
const handleImportSuccess = (response) => {
  if (response.success) {
    ElMessage.success(response.message)
    loadRecords()  // 刷新列表
  } else {
    ElMessage.error(response.message)
  }
}

// Excel导入失败
const handleImportError = (error) => {
  ElMessage.error('导入失败: ' + error.message)
}
```

---

## 5. 更新统计信息卡片

### 位置：报工管理页面底部（约第320-340行）

### 原代码（只显示总工时）：
```vue
<el-card style="margin-top: 20px;">
  <template #header>
    <span>📊 统计信息</span>
  </template>
  <el-statistic title="总工时" :value="totalHours">
    <template #suffix>小时</template>
  </el-statistic>
</el-card>
```

### 新代码（显示完整统计）：
```vue
<el-card style="margin-top: 20px;" v-if="statistics">
  <template #header>
    <span>📊 工时统计</span>
  </template>
  <el-row :gutter="20">
    <el-col :span="6">
      <el-statistic title="正常工时" :value="statistics.total_normal_hours">
        <template #suffix>小时</template>
      </el-statistic>
    </el-col>
    <el-col :span="6">
      <el-statistic title="加班工时" :value="statistics.total_overtime_hours">
        <template #suffix>小时</template>
      </el-statistic>
    </el-col>
    <el-col :span="6">
      <el-statistic title="总工时" :value="statistics.total_hours">
        <template #suffix>小时</template>
      </el-statistic>
    </el-col>
    <el-col :span="6">
      <el-statistic title="人天" :value="statistics.person_days" />
    </el-col>
    <el-col :span="6">
      <el-statistic title="人月" :value="statistics.person_months" />
    </el-col>
  </el-row>
  <div style="margin-top: 10px; color: #909399; font-size: 12px;">
    💡 8小时 = 1人天，21.75天 = 1人月
  </div>
</el-card>
```

---

## 6. 更新统计数据获取

### 位置：loadRecords 方法（约第640行）

### 原代码（自己计算统计）：
```js
const loadRecords = async () => {
  try {
    loading.value = true
    const res = await axios.get('/api/records')
    if (res.data.success) {
      records.value = res.data.data
      // 自己计算统计...
    }
  }
}
```

### 新代码（使用后端返回的统计）：
```js
const loadRecords = async () => {
  try {
    loading.value = true
    const res = await axios.get('/api/records')
    if (res.data.success) {
      records.value = res.data.data
      statistics.value = res.data.statistics  // 直接使用后端统计
    }
  } catch (error) {
    ElMessage.error('加载记录失败: ' + error.message)
  } finally {
    loading.value = false
  }
}
```

### 添加statistics变量定义（约第395行）：
```js
const statistics = ref(null)
```

---

## 7. 修复Icon导入

### 位置：<script setup> 最上方

### 确保导入了所有需要的Icon：
```js
import { DocumentAdd, Refresh, Upload, Download } from '@element-plus/icons-vue'
```

---

## 快速应用方法

### 方法1：手动修改
按照上述说明，在 `frontend/src/App.vue` 中找到对应位置，逐个修改。

### 方法2：完全重写（推荐）
由于改动较多，建议重新创建App.vue：

```bash
cd frontend/src
mv App.vue App.vue.old
# 然后创建新的App.vue，参考Agent.md中的前端修改要点
```

### 方法3：使用Git对比
```bash
# 查看Agent.md中提供的完整代码示例
# 对比现有文件
git diff App.vue
```

---

## 测试清单

修改完成后，测试以下功能：

- [ ] 配置管理：curl命令解析正常
- [ ] 生成记录：日期范围选择器显示正确
- [ ] 生成记录：点击生成后能调用新API
- [ ] 记录列表：统计卡片显示人天和人月
- [ ] Excel导出：点击后能下载xlsx文件
- [ ] Excel导入：选择文件后能上传并更新数据
- [ ] 刷新记录：统计数据正确更新

---

## 如果遇到问题

### 问题1：日期选择器不显示
**解决**：确保 Element Plus 版本 >= 2.4.0
```bash
npm install element-plus@latest
```

### 问题2：Excel上传失败
**检查**：
1. action地址是否正确：`/api/excel/import`
2. accept属性是否设置：`.xlsx,.xls`
3. 后端handler是否正确处理`multipart/form-data`

### 问题3：统计数据不显示
**检查**：
1. `statistics.value` 是否正确赋值
2. `v-if="statistics"` 条件是否满足
3. 后端是否正确返回 `statistics` 字段

---

**更新日期**：2025-12-31
**对应后端版本**：2.0.0
