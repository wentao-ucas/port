<template>
  <!-- ===== 登录门禁 ===== -->
  <div v-if="!accessToken" class="login-wrap">
    <div class="login-card">
      <div class="login-brand"><span class="brand-dot"></span> 工时报工系统</div>
      <p class="login-sub">请登录后使用</p>
      <div class="login-field">
        <label>账号</label>
        <input v-model="loginForm.username" placeholder="账号" @keyup.enter="doLogin" autocomplete="username" />
      </div>
      <div class="login-field">
        <label>密码</label>
        <input v-model="loginForm.password" type="password" placeholder="密码" @keyup.enter="doLogin" autocomplete="current-password" />
      </div>
      <button class="btn btn-primary login-btn" :disabled="loginLoading" @click="doLogin">
        <span v-if="loginLoading" class="spinner"></span> 登 录
      </button>
    </div>
    <div class="login-foot">工时报工 · 内部工具</div>
  </div>

  <!-- ===== 主应用 ===== -->
  <div v-else class="layout">
    <aside class="sidebar">
      <div class="brand"><span class="brand-dot"></span><span>工时报工</span></div>

      <nav class="nav">
        <a class="nav-item" :class="{ active: view === 'calendar' }" @click="switchView('calendar')">
          <span class="nav-ico">📅</span> 可报工时日历
        </a>
        <a class="nav-item" :class="{ active: view === 'records' }" @click="switchView('records')">
          <span class="nav-ico">📝</span> 工时记录
          <span v-if="todoCount > 0" class="nav-badge">{{ todoCount }}</span>
        </a>
        <a class="nav-item" :class="{ active: view === 'tasks' }" @click="switchView('tasks')">
          <span class="nav-ico">📋</span> 我的任务
        </a>
        <a class="nav-item" :class="{ active: view === 'config' }" @click="switchView('config')">
          <span class="nav-ico">⚙️</span> 认证配置
        </a>
      </nav>

      <div class="side-user">
        <template v-if="currentUser.username">
          <div class="su-avatar">{{ (currentUser.display_name || '?').slice(0, 1).toUpperCase() }}</div>
          <div class="su-meta">
            <div class="su-name">{{ currentUser.display_name }}</div>
            <div class="su-id">已认证</div>
          </div>
        </template>
        <div v-else class="su-empty">未配置 · 请先认证</div>
        <button class="su-logout" title="退出登录" @click="logoutAll">⎋</button>
      </div>
    </aside>

    <main class="content">
      <div v-if="tokenStatus" :style="{background: tokenStatus.level==='expired' ? '#fde8e6' : '#fff4e0', color: tokenStatus.level==='expired' ? '#b42318' : '#9a6700', padding:'10px 16px', borderRadius:'8px', margin:'0 0 14px', display:'flex', alignItems:'center', gap:'10px', fontSize:'14px'}">
        <span>{{ tokenStatus.level === 'expired' ? '⛔' : '⏰' }}</span>
        <span style="flex:1">{{ tokenStatus.text }}</span>
        <button class="btn" @click="switchView('config')">去更新认证</button>
      </div>
      <!-- ===== 可报工时日历 ===== -->
      <section v-show="view === 'calendar'">
        <div class="page-head">
          <div>
            <h2>可报工时日历</h2>
            <p class="sub">每天可填报的正常 / 加班工时，按月自动查询</p>
          </div>
          <div class="head-actions">
            <el-date-picker
              v-model="calendarDate"
              type="month"
              :clearable="false"
              format="YYYY 年 M 月"
              placeholder="跳到年月"
              style="width: 150px;"
            />
            <button class="btn" @click="goToday">回到本月</button>
            <button class="btn" :disabled="queryLoading" @click="queryMonth(true)">
              <span v-if="queryLoading" class="spinner"></span> 刷新本月
            </button>
          </div>
        </div>

        <div v-if="!currentUser.username" class="card empty">请先在「认证配置」粘贴 curl 完成认证</div>

        <template v-else>
          <div class="sum-grid">
            <div class="sum-card"><div class="sum-label">本月可填天数</div><div class="sum-num">{{ monthSummary.days }}</div></div>
            <div class="sum-card"><div class="sum-label">可填正常工时合计</div><div class="sum-num">{{ monthSummary.n }}</div></div>
            <div class="sum-card"><div class="sum-label">可填加班工时合计</div><div class="sum-num">{{ monthSummary.o }}</div></div>
          </div>

          <div v-if="!canSubmit" class="warn-banner">
            ⚠ 当前配置只能查询。可以生成待填报列表，但<b>提交报工</b>需要用 <b>reportWorkingHours</b> 的 cURL 重新配置。
          </div>

          <div class="card cal-card">
            <div class="fill-bar">
              <div class="fb-left">
                <span class="fb-tip">点选 / 按住拖动选要填的天（可翻月累加）→</span>
                <span class="fb-sel">已选 <b>{{ selectedCount }}</b> 天 · 合计 正 {{ selSummary.n }} / 加 {{ selSummary.o }}</span>
              </div>
              <div class="fb-right">
                <button class="btn" @click="selectThisWeek">全选本周可填</button>
                <button class="btn" @click="selectAllFillable">全选本月可填</button>
                <button class="btn" @click="clearSel" :disabled="!selectedCount">清空</button>
                <button class="btn btn-primary" @click="generateDraft" :disabled="!selectedCount || fillLoading">
                  <span v-if="fillLoading" class="spinner"></span> 生成待填报 ({{ selectedCount }})
                </button>
              </div>
            </div>

            <div class="legend">
              <span><i class="dot has"></i>工作日可填</span>
              <span><i class="dot ot"></i>周末/节假日可加班(手动选)</span>
              <span><i class="dot zero"></i>为 0</span>
              <span><i class="dot weekend"></i>周末/休</span>
              <span><i class="dot sel"></i>已选中</span>
              <span class="lg-badge hol">节</span>法定节假日
              <span class="lg-badge mk">班</span>调休补班
            </div>

            <el-calendar v-model="calendarDate" v-loading="queryLoading">
              <template #date-cell="{ data }">
                <div class="cal-cell" :class="[cellClass(data), { sel: !!selectedMap?.[data.day] }]"
                  @mousedown.prevent="startDrag(data)" @mouseenter="dragOver(data)">
                  <span class="cal-day">
                    {{ data.day.split('-')[2] }}
                    <i v-if="selectedMap?.[data.day]" class="sel-check">✓</i>
                    <span v-if="holidayName(data.day)" class="cal-badge hol">{{ holidayName(data.day) }}</span>
                    <span v-else-if="isMakeup(data.day)" class="cal-badge mk">班</span>
                  </span>
                  <div class="cal-hours" v-if="data.type === 'current-month' && qmap?.[data.day]">
                    <template v-if="qmap[data.day].status === 'success'">
                      <span class="ch-n">正 {{ qmap[data.day].normal_hours || 0 }}</span>
                      <span class="ch-o">加 {{ qmap[data.day].overtime_hours || 0 }}</span>
                    </template>
                    <span v-else class="ch-err">失败</span>
                  </div>
                </div>
              </template>
            </el-calendar>
          </div>
        </template>
      </section>

      <!-- ===== 工时记录 ===== -->
      <section v-show="view === 'records'">
        <div class="page-head">
          <div>
            <h2>工时记录</h2>
            <p class="sub">在日历点选要填的天 → 生成待填报 → 这里编辑 → 勾选提交</p>
          </div>
          <div class="head-actions">
            <button class="btn" @click="loadRecords" :disabled="loading">刷新</button>
            <button class="btn btn-danger" @click="deleteSelected" :disabled="selectedRecords.length === 0">
              删除所选 ({{ selectedRecords.length }})
            </button>
            <button v-show="activeTab === 'todo'" class="btn btn-primary" @click="submitSelectedRecords" :disabled="selectedRecords.length === 0 || loading">
              提交所选 ({{ selectedRecords.length }})
            </button>
          </div>
        </div>

        <div v-if="!currentUser.username" class="card empty">请先在「认证配置」完成认证</div>

        <template v-else>
          <div v-if="reportTask" class="card report-task-bar">
            <span class="rt-label">本次报工任务</span>
            <span class="rt-name">{{ reportTask.rwMc }}</span>
            <span v-if="reportTask.xmName" class="rt-item">项目：{{ reportTask.xmName }}</span>
            <span v-if="reportTask.rwZt" class="tag" :style="{ background: taskStStyle(reportTask.rwZt).bg, color: taskStStyle(reportTask.rwZt).c }">{{ reportTask.rwZt }}</span>
            <span v-if="reportTask.ks && reportTask.js" class="rt-item">计划周期：{{ reportTask.ks }} ~ {{ reportTask.js }}</span>
            <span v-if="!reportTask.matched" class="rt-tip">（项目/状态需在「我的任务」能匹配到才显示）</span>
          </div>
          <div v-if="!canSubmit" class="warn-banner">
            ⚠ 当前配置只能查询、不能提交报工。请用 <b>reportWorkingHours</b> 的 cURL 重新配置后再提交。
          </div>
          <el-tabs v-model="activeTab" class="rec-tabs">
            <el-tab-pane name="todo" :label="`待处理 (${todoCount})`" />
            <el-tab-pane name="history" :label="`历史记录 (${historyCount})`" />
          </el-tabs>
          <div class="card toolbar">
            <span class="tb-count">共 {{ filteredRecords.length }} 条</span>
            <template v-if="activeTab === 'todo'">
              <button class="btn" @click="selectAllTodo" :disabled="!filteredRecords.length">全选全部 ({{ filteredRecords.length }})</button>
              <button class="btn" @click="clearRecSel" :disabled="!selectedRecords.length">清空选择 ({{ selectedRecords.length }})</button>
            </template>
            <span style="flex:1"></span>
            <span class="tb-hint" v-if="activeTab === 'todo'">表头勾选=本页；跨页全选用「全选全部」；失败的勾选后可再次「提交所选」补提交</span>
            <span class="tb-hint" v-else>已提交的历史记录；如需改动可删除后在日历重新生成</span>
          </div>

          <div class="card batch-bar" v-show="activeTab === 'todo'">
            <span class="tb-label">批量改整列（当前 {{ filteredRecords.length }} 条）：</span>
            <span class="bb-item">正常
              <el-input-number v-model="batch.normal" :min="0" :max="8" :step="0.5" :precision="1" size="small" style="width:96px" />
              <button class="btn" @click="applyBatch('normal')">应用</button>
            </span>
            <span class="bb-item">加班
              <el-input-number v-model="batch.overtime" :min="0" :max="8" :step="0.5" :precision="1" size="small" style="width:96px" />
              <button class="btn" @click="applyBatch('overtime')">应用</button>
            </span>
            <span class="bb-item">内容
              <el-input v-model="batch.content" size="small" style="width:200px" placeholder="工作内容" />
              <button class="btn" @click="applyBatch('content')">应用</button>
            </span>
            <span class="tb-hint">工时按每天「可填上限」自动封顶</span>
          </div>

          <div class="card">
            <el-table :data="pagedRecords" @selection-change="handleSelectionChange" ref="recTable" row-key="id" style="width:100%">
              <el-table-column type="selection" width="46" reserve-selection />
              <el-table-column label="日期" width="150">
                <template #default="scope">
                  <span>{{ scope.row.date }}</span>
                  <!-- 超期只对"待处理"有意义(它们才会按当前任务提交)；历史记录已提交、可能属于别的任务，
                       而记录不绑任务，拿当前任务周期去量会误判，故历史 tab 不显示超期 -->
                  <span v-if="activeTab === 'todo' && isOutOfRange(scope.row.date)" class="tag tag-red" style="margin-left:6px"
                    title="报工日期不在任务计划周期内">超期</span>
                </template>
              </el-table-column>
              <el-table-column label="星期" width="74">
                <template #default="scope">
                  <span class="tag" :class="weekendTag(scope.row.date)">{{ getWeekdayName(scope.row.date) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="正常工时" width="130">
                <template #default="scope">
                  <el-input-number v-if="activeTab === 'todo'" v-model="scope.row.normal_hours" :min="0" :max="Math.min(8, scope.row.avail_normal ?? 8)"
                    :step="0.5" :precision="1" size="small" controls-position="right" style="width:112px"
                    @change="() => saveRow(scope.row)" />
                  <span v-else class="ro-val">{{ scope.row.normal_hours }}</span>
                </template>
              </el-table-column>
              <el-table-column label="加班工时" width="130">
                <template #default="scope">
                  <el-input-number v-if="activeTab === 'todo'" v-model="scope.row.overtime_hours" :min="0" :max="Math.min(8, scope.row.avail_overtime ?? 8)"
                    :step="0.5" :precision="1" size="small" controls-position="right" style="width:112px"
                    @change="() => saveRow(scope.row)" />
                  <span v-else class="ro-val">{{ scope.row.overtime_hours }}</span>
                </template>
              </el-table-column>
              <el-table-column label="可填上限" width="96">
                <template #default="scope">
                  <span class="cap-hint" v-if="scope.row.avail_normal != null">正{{ scope.row.avail_normal }} / 加{{ scope.row.avail_overtime }}</span>
                  <span class="cap-hint" v-else>—</span>
                </template>
              </el-table-column>
              <el-table-column label="工作内容" min-width="200">
                <template #default="scope">
                  <el-input v-if="activeTab === 'todo'" v-model="scope.row.work_content" size="small" placeholder="工作内容" @change="() => saveRow(scope.row)" />
                  <span v-else class="ro-val">{{ scope.row.work_content || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="96">
                <template #default="scope">
                  <span class="tag" :class="statusTag(scope.row.status)">{{ statusMap[scope.row.status] || scope.row.status }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="160" />
              <el-table-column label="操作" width="64" fixed="right">
                <template #default="scope">
                  <a class="link danger" @click="deleteRow(scope.row)">删除</a>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="filteredRecords.length > pageSize" style="margin-top:12px;display:flex;justify-content:center">
              <el-pagination
                layout="prev, pager, next, total"
                :total="filteredRecords.length"
                :page-size="pageSize"
                v-model:current-page="currentPage"
                background small />
            </div>
          </div>

          <div v-if="filteredRecords.length" class="sum-grid five">
            <div class="sum-card"><div class="sum-label">正常工时</div><div class="sum-num">{{ liveStats.total_normal_hours }}</div></div>
            <div class="sum-card"><div class="sum-label">加班工时</div><div class="sum-num">{{ liveStats.total_overtime_hours }}</div></div>
            <div class="sum-card"><div class="sum-label">总工时</div><div class="sum-num">{{ liveStats.total_hours }}</div></div>
            <div class="sum-card"><div class="sum-label">人天</div><div class="sum-num">{{ liveStats.person_days }}</div></div>
            <div class="sum-card"><div class="sum-label">人月</div><div class="sum-num">{{ liveStats.person_months }}</div></div>
          </div>
          <p v-if="filteredRecords.length" class="hint">8小时 = 1人天，21.75天 = 1人月　·　工时直接在列里改，不超过「可填上限」</p>
        </template>
      </section>

      <!-- ===== 提交进度 ===== -->
      <el-dialog v-model="submitting" title="正在提交报工" width="460px" append-to-body
        :close-on-click-modal="false" :close-on-press-escape="false" :show-close="false">
        <div class="submit-prog">
          <el-progress :percentage="submitPct" :status="submitFail ? 'warning' : ''" :stroke-width="14" />
          <p class="sp-stat">已完成 {{ submitDone }} / {{ submitItems.length }}　·　成功 {{ submitOk }}　失败 {{ submitFail }}</p>
          <ul class="sp-list">
            <li v-for="it in submitItems" :key="it.id" :class="'sp-' + it.state">
              <span class="sp-ico">
                <span v-if="it.state === 'doing'" class="spinner"></span>
                <span v-else-if="it.state === 'ok'">✓</span>
                <span v-else-if="it.state === 'fail'">✗</span>
                <span v-else>·</span>
              </span>
              <span class="sp-date">{{ it.date }}</span>
              <span class="sp-err" v-if="it.state === 'fail'">{{ it.error }}</span>
            </li>
          </ul>
          <p class="sp-tip">提交期间请勿关闭页面…</p>
        </div>
      </el-dialog>

      <!-- ===== 我的任务 ===== -->
      <section v-show="view === 'tasks'">
        <div class="page-head">
          <div>
            <h2>我的任务</h2>
            <p class="sub">从效控平台拉取你的填报任务，进行中的排在最前面</p>
          </div>
          <div class="head-actions">
            <button class="btn" @click="loadTasks" :disabled="tasksLoading">
              <span v-if="tasksLoading" class="spinner"></span> 刷新
            </button>
          </div>
        </div>

        <div v-if="!currentUser.username" class="card empty">请先在「认证配置」完成认证</div>

        <template v-else>
          <div class="card toolbar">
            <span class="tb-label">状态筛选：</span>
            <el-select v-model="taskStatusFilter" placeholder="全部" style="width:120px" size="small">
              <el-option label="全部" value="" />
              <el-option label="进行中" value="进行中" />
              <el-option label="未开始" value="未开始" />
              <el-option label="已暂停" value="已暂停" />
              <el-option label="已完成" value="已完成" />
            </el-select>
            <span class="tb-count">共 {{ filteredTasks.length }} 个 · 进行中 {{ ongoingCount }} 个</span>
          </div>
          <div class="card">
            <el-table :data="pagedTasks" v-loading="tasksLoading" style="width:100%">
              <el-table-column prop="rwMc" label="任务名称" min-width="170" />
              <el-table-column prop="ssXm" label="所属项目" min-width="240" show-overflow-tooltip />
              <el-table-column label="状态" width="92">
                <template #default="scope">
                  <span :style="{padding:'2px 9px',borderRadius:'10px',fontSize:'12px',background: taskStStyle(scope.row.rwZt).bg, color: taskStStyle(scope.row.rwZt).c}">{{ scope.row.rwZt }}</span>
                </template>
              </el-table-column>
              <el-table-column label="计划起止" width="196">
                <template #default="scope">{{ scope.row.jhKsDate }} ~ {{ scope.row.jhJsDate }}</template>
              </el-table-column>
              <el-table-column prop="roleName" label="角色" width="84" />
              <el-table-column label="逾期" width="80">
                <template #default="scope">
                  <span :style="{color: scope.row.yqTs>0 ? '#b42318':'#bbb'}">{{ scope.row.yqTs>0 ? scope.row.yqTs+'天' : '—' }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="filteredTasks.length > taskPageSize" style="margin-top:12px;display:flex;justify-content:center">
              <el-pagination
                layout="prev, pager, next, total"
                :total="filteredTasks.length"
                :page-size="taskPageSize"
                v-model:current-page="taskPage"
                background small />
            </div>
          </div>
        </template>
      </section>

      <!-- ===== 认证配置 ===== -->
      <section v-show="view === 'config'">
        <div class="page-head">
          <div>
            <h2>认证配置</h2>
            <p class="sub">粘贴浏览器抓到的 curl，系统自动识别身份与认证</p>
          </div>
        </div>

        <el-tabs v-model="configMode" class="rec-tabs">
          <el-tab-pane label="完整模式（推荐）" name="full" />
          <el-tab-pane label="懒人模式" name="lazy" />
        </el-tabs>

        <!-- 懒人模式：任意认证 + 选任务，系统自动合成提交配置 -->
        <div v-show="configMode === 'lazy'" class="card">
          <!-- 未开启：风险提示 + 开启确认 -->
          <div v-if="!lazyEnabled">
            <div :style="{background:'#fff4e0',color:'#9a6700',padding:'14px 16px',borderRadius:'8px',fontSize:'14px',lineHeight:'1.7'}">
              ⚠ <b>懒人模式说明（请先了解）</b><br>
              懒人模式会按「已知规律」<b>自动推测合成</b>报工字段（工作类型、任务状态、type 等）。这些规律是从少量样本总结的，<b>未必对所有项目/任务都准确</b>，极端情况下可能报上不对的数据。<br>
              <b>最稳妥仍是「完整模式」</b>——直接粘你真实的 reportWorkingHours curl，那是原系统真实发出的、字段一定对。<br>
              了解上述风险、想图省事，再开启懒人模式。
            </div>
            <div class="form-actions" style="margin-top:14px">
              <button class="btn" @click="configMode = 'full'">用完整模式（推荐）</button>
              <button class="btn btn-primary" @click="lazyEnabled = true">我已了解风险，开启懒人模式</button>
            </div>
          </div>

          <!-- 已开启：填写区 -->
          <template v-else>
          <div class="form-group">
            <label class="form-label">粘一条已登录请求的 curl（getMyTask / CurrentUser 等都行，好抓）</label>
            <el-input v-model="lazyCurl" type="textarea" :rows="6"
              placeholder="从 Network 随便复制一条带认证的 curl 即可，不用费劲找 reportWorkingHours..." />
            <p class="form-hint">
              ① 先按 <b>F12</b> 打开开发者工具，切到 <b>Network</b> 标签并保持打开<br>
              ② 登录/打开 <b>xiaokong.cfid.cn</b> 后随便操作一下（刷新或点页面），让请求出现<br>
              ③ 在 Network 里找到<b>任意一条</b>发往 xiaokong 的请求（<b>getMyTask</b> / <b>CurrentUser</b> / <b>getInitMsg</b> 都行）→ 右键 <b>Copy → Copy as cURL (bash)</b><br>
              ④ 粘贴到上方（含认证即可，不用费劲找 reportWorkingHours，其余字段系统按规律自动合成）
            </p>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" @click="lazyLoadTasks" :disabled="!lazyCurl || lazyLoading">
              <span v-if="lazyLoading" class="spinner"></span> 拉取我的任务
            </button>
            <span v-if="lazyDisplayName" class="hint" style="margin-left:10px">已识别身份：<b>{{ lazyDisplayName }}</b></span>
          </div>
          <div v-if="lazyTasks.length" class="form-group" style="margin-top:14px">
            <label class="form-label">选一个任务（{{ lazyTasks.length }} 个）</label>
            <el-select v-model="lazyTaskId" filterable placeholder="选择要报工的任务" style="width:100%">
              <el-option v-for="t in lazyTasks" :key="t.id" :value="t.id"
                :label="`${t.rwMc} · ${t.ssXm}（${t.jhKsDate}~${t.jhJsDate}）`" />
            </el-select>
          </div>
          <div v-if="lazyTasks.length" class="form-actions">
            <button class="btn btn-primary" @click="saveLazyConfig" :disabled="!lazyTaskId || loading">
              完成配置（之后即可直接提交报工）
            </button>
          </div>
          </template>
        </div>

        <!-- 完整模式：粘 reportWorkingHours 的 curl（一次到位） -->
        <div v-show="configMode === 'full'" class="card">
          <div class="form-group">
            <label class="form-label">Curl 命令</label>
            <el-input v-model="config.curl_template" type="textarea" :rows="8"
              placeholder="从浏览器开发者工具粘贴完整的 curl 命令..." @blur="parseCurlCommand" />
            <p class="form-hint">
              ① 先按 <b>F12</b> 打开开发者工具，切到 <b>Network</b> 标签并保持打开<br>
              ② 在原系统正常提交一次报工<br>
              ③ 在 Network 里找到 <b>reportWorkingHours</b> 请求 → 右键 <b>Copy → Copy as cURL (bash)</b><br>
              ④ 粘贴到上方（这一条同时含 身份 + 查询凭证 + 提交模板，一次到位）<br>
              <span class="hint-tip">只想查询/识别身份：登录后随便复制一个已登录请求（如 getInitMsg）的 cURL 即可；但提交报工必须用 reportWorkingHours 那条。</span>
            </p>
          </div>

          <div class="parsed-grid">
            <div class="parsed-item">
              <span class="pi-label">身份识别</span>
              <span class="tag" :class="parsedInfo.authorization ? 'tag-green' : 'tag-gray'">
                {{ parsedInfo.authorization ? '已识别 Authorization' : '未识别' }}
              </span>
            </div>
            <div class="parsed-item">
              <span class="pi-label">Cookie</span>
              <span class="tag" :class="parsedInfo.cookie ? 'tag-green' : 'tag-gray'">{{ parsedInfo.cookie ? '已识别' : '未识别' }}</span>
            </div>
            <div class="parsed-item">
              <span class="pi-label">提交模板</span>
              <span class="tag" :class="parsedInfo.template_data ? 'tag-green' : 'tag-gray'">{{ parsedInfo.template_data ? '已识别' : '未识别' }}</span>
            </div>
          </div>

          <div v-if="parsedInfo.templateDataPreview" class="form-group">
            <label class="form-label">模板预览</label>
            <pre class="code-pre">{{ parsedInfo.templateDataPreview }}</pre>
          </div>

          <div class="form-actions">
            <button class="btn btn-primary" @click="saveConfig" :disabled="!config.curl_template || loading">保存配置</button>
            <button class="btn" v-if="parsedInfo.authorization" @click="testConfig" :disabled="loading">测试配置</button>
          </div>
        </div>
      </section>
    </main>


  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { HOLIDAYS, MAKEUP_WORKDAYS } from './holidays'

// 开发：直连本地后端 18760（靠 CORS）；生产：相对路径，由 nginx 反代 /worktime-api 到后端
const API_BASE = import.meta.env.DEV ? 'http://localhost:18760' : ''
axios.defaults.baseURL = API_BASE

// ===== 访问门禁 =====
const accessToken = ref(localStorage.getItem('worktime_access') || '')
const loginForm = ref({ username: '', password: '' })
const loginLoading = ref(false)

// ===== 业务身份 =====
const currentUser = ref({ username: '', display_name: '' })

axios.interceptors.request.use((cfg) => {
  if (accessToken.value) cfg.headers['X-Access-Token'] = accessToken.value
  if (currentUser.value.username) cfg.params = { ...(cfg.params || {}), username: currentUser.value.username }
  return cfg
})
axios.interceptors.response.use((r) => r, (err) => {
  if (err.response && err.response.status === 401 && err.config && !err.config.url.includes('/login')) {
    accessToken.value = ''
    localStorage.removeItem('worktime_access')
    ElMessage.warning('登录已过期，请重新登录')
  }
  return Promise.reject(err)
})


const view = ref('config')
const loading = ref(false)

const config = ref({ authorization: '', cookie: '', curl_template: '' })
const parsedInfo = ref({ authorization: '', cookie: '', url: '', template_data: null, templateDataPreview: '' })

const calendarDate = ref(new Date())
const qmap = ref({})
const queryLoading = ref(false)
const canSubmit = ref(false)            // 当前配置能否填报（reportWorkingHours 的 cURL 才行）
const selectedMap = ref({})             // 跨月累加选择：{ 'YYYY-MM-DD': {normal_hours, overtime_hours} }
const fillLoading = ref(false)
const selectedCount = computed(() => Object.keys(selectedMap.value).length)
const selSummary = computed(() => {
  let n = 0, o = 0
  for (const k in selectedMap.value) {
    const r = selectedMap.value[k]
    n += parseFloat(r.normal_hours || 0); o += parseFloat(r.overtime_hours || 0)
  }
  return { n: +n.toFixed(1), o: +o.toFixed(1) }
})
const monthSummary = computed(() => {
  let n = 0, o = 0, days = 0
  for (const k in qmap.value) {
    const r = qmap.value[k]
    if (r.status === 'success') {
      const nn = parseFloat(r.normal_hours || 0), oo = parseFloat(r.overtime_hours || 0)
      n += nn; o += oo
      if (nn + oo > 0) days++
    }
  }
  return { days, n: +n.toFixed(1), o: +o.toFixed(1) }
})

const records = ref([])
const selectedRecords = ref([])
const statistics = ref(null)
// 提交进度（前端逐条并发：实时显示提交到哪条 + 成败）
const submitting = ref(false)
const submitItems = ref([])   // [{id, date, state:'wait'|'doing'|'ok'|'fail', error}]
const submitDone = computed(() => submitItems.value.filter(i => i.state === 'ok' || i.state === 'fail').length)
const submitOk = computed(() => submitItems.value.filter(i => i.state === 'ok').length)
const submitFail = computed(() => submitItems.value.filter(i => i.state === 'fail').length)
const submitPct = computed(() => submitItems.value.length ? Math.round(submitDone.value / submitItems.value.length * 100) : 0)
// 任务计划周期：懒人模式取模板里的 _jhKsDate/_jhJsDate；完整模式模板没有这俩字段，
// 改为按任务ID从已加载的 getMyTask 列表里匹配拿周期，两种模式都能判超期。
const taskPeriod = computed(() => {
  const td = parsedInfo.value.template_data || {}
  const m = td.gstbRwId ? tasks.value.find(t => String(t.id) === String(td.gstbRwId)) : null
  return {
    ks: (m && m.jhKsDate) || td._jhKsDate || '',
    js: (m && m.jhJsDate) || td._jhJsDate || '',
  }
})
// 报工日期是否超出任务计划周期（早于开始 或 晚于结束）。无周期信息时一律不算超期
const isOutOfRange = (date) => {
  const { ks, js } = taskPeriod.value
  if (!ks || !js || !date) return false
  return date < ks || date > js
}
const pendingCount = computed(() => records.value.filter(r => r.status === 'pending').length)
// 记录页分两 tab：待处理(pending+failed) / 历史记录(submitted)
const activeTab = ref('todo')
const todoCount = computed(() => records.value.filter(r => r.status === 'pending' || r.status === 'failed').length)
const historyCount = computed(() => records.value.filter(r => r.status === 'submitted').length)
const batch = ref({ normal: 8, overtime: 0, content: '' })
const filteredRecords = computed(() =>
  activeTab.value === 'history'
    ? records.value.filter(r => r.status === 'submitted')
    : records.value.filter(r => r.status === 'pending' || r.status === 'failed')
)
// 统计随列内编辑实时变化（按当前 tab 的记录算）
const liveStats = computed(() => {
  let n = 0, o = 0
  for (const r of filteredRecords.value) { n += parseFloat(r.normal_hours || 0); o += parseFloat(r.overtime_hours || 0) }
  const total = n + o
  return {
    total_normal_hours: +n.toFixed(2),
    total_overtime_hours: +o.toFixed(2),
    total_hours: +total.toFixed(2),
    person_days: +(total / 8).toFixed(2),
    person_months: +(total / 8 / 21.75).toFixed(2)
  }
})

// 分页：两个 tab 都分页(10条/页)。待处理跨页全选靠「全选全部」按钮 + el-table reserve-selection
const pageSize = ref(10)
const currentPage = ref(1)
const recTable = ref(null)   // el-table 引用，用于跨页全选/清空
const pagedRecords = computed(() => {
  const s = (currentPage.value - 1) * pageSize.value
  return filteredRecords.value.slice(s, s + pageSize.value)
})
watch(activeTab, () => { currentPage.value = 1; recTable.value?.clearSelection(); selectedRecords.value = [] })

// 本次报工对应的任务信息（两种模式都显示，让用户心里有数）：
// 任务名取模板 gstbRwmc；项目名/状态/计划周期优先用 getMyTask 匹配到的(更全)，匹配不到则退回模板里的
const reportTask = computed(() => {
  const td = parsedInfo.value.template_data
  if (!td || !td.gstbRwId) return null
  const m = tasks.value.find(t => String(t.id) === String(td.gstbRwId))
  return {
    rwMc: (m && m.rwMc) || td.gstbRwmc || '—',
    xmName: (m && m.ssXm) || '',
    rwZt: (m && m.rwZt) || '',
    ks: (m && m.jhKsDate) || td._jhKsDate || '',
    js: (m && m.jhJsDate) || td._jhJsDate || '',
    matched: !!m,
  }
})
watch(() => filteredRecords.value.length, () => {
  const max = Math.max(1, Math.ceil(filteredRecords.value.length / pageSize.value))
  if (currentPage.value > max) currentPage.value = max
})

const statusMap = { pending: '待提交', submitted: '已提交', failed: '提交失败' }

// 认证 token 过期提醒（token_exp 来自后端解析 JWT 的 exp，毫秒）
const tokenExp = ref(null)
const tokenStatus = computed(() => {
  if (!tokenExp.value || !currentUser.value.username) return null
  const remainH = (tokenExp.value - Date.now()) / 3600000
  if (remainH <= 0) return { level: 'expired', text: '认证已过期，请到「认证配置」重新粘贴最新的 curl，否则查询和提交都会失败。' }
  if (remainH < 2) return { level: 'soon', text: `认证约 ${remainH.toFixed(1)} 小时后过期，建议尽快到「认证配置」重新粘贴 curl。` }
  return null
})

// ===== 登录 =====
const doLogin = async () => {
  if (!loginForm.value.username || !loginForm.value.password) { ElMessage.warning('请输入账号和密码'); return }
  try {
    loginLoading.value = true
    const res = await axios.post('/worktime-api/login', loginForm.value)
    if (res.data.success) {
      accessToken.value = res.data.token
      localStorage.setItem('worktime_access', res.data.token)
      loginForm.value.password = ''
      ElMessage.success('登录成功')
      await bootstrap()
    } else {
      ElMessage.error(res.data.message || '登录失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '账号或密码错误')
  } finally { loginLoading.value = false }
}
const logoutAll = () => {
  accessToken.value = ''
  localStorage.removeItem('worktime_access')
  currentUser.value = { username: '', display_name: '' }
  localStorage.removeItem('worktime_user')
  records.value = []; statistics.value = null; qmap.value = {}
  monthCache.value = {}; tasks.value = []   // 退出也清掉按用户的内存缓存，防止换人登录串数据
  // 退出彻底清空认证配置/解析结果/懒人模式状态，杜绝 token/curl 残留给下一个人（尤其共用电脑）
  config.value = { authorization: '', cookie: '', curl_template: '' }
  parsedInfo.value = { authorization: '', cookie: '', url: '', template_data: null, templateDataPreview: '' }
  canSubmit.value = false
  tokenExp.value = null
  lazyCurl.value = ''; lazyTasks.value = []; lazyTaskId.value = ''; lazyDisplayName.value = ''; lazyEnabled.value = false
  configMode.value = 'full'
  view.value = 'config'
}

// ===== 业务身份持久化 =====
const setUser = (username, display_name) => {
  // 切换到不同业务身份时，清掉上一个人的所有按用户内存状态，防止同浏览器不刷新切 curl 串数据
  if (currentUser.value.username && currentUser.value.username !== username) {
    monthCache.value = {}; qmap.value = {}; tasks.value = []
    records.value = []; statistics.value = null
    selectedMap.value = {}; selectedRecords.value = []   // 日历选择 + 表格勾选也属上一个人
    tokenExp.value = null                                 // 认证过期横幅别沿用上一个人的
  }
  currentUser.value = { username, display_name: display_name || username }
  localStorage.setItem('worktime_user', JSON.stringify(currentUser.value))
}

const switchView = (v) => {
  view.value = v
  if (v === 'calendar' && currentUser.value.username && Object.keys(qmap.value).length === 0) queryMonth()
  if (v === 'tasks' && currentUser.value.username && tasks.value.length === 0) loadTasks()
  // 进记录页也拉一次任务，用于「本次报工任务」条显示项目名/状态/计划周期（拉取失败则只显示任务名，不影响报工）
  if (v === 'records' && currentUser.value.username && tasks.value.length === 0) loadTasks()
}

// ===== 我的任务 =====
const tasks = ref([])
const tasksLoading = ref(false)
const loadTasks = async () => {
  if (!currentUser.value.username) return
  try {
    tasksLoading.value = true
    const res = await axios.post('/worktime-api/my-tasks')
    if (res.data.success) tasks.value = res.data.data || []
    else if (looksExpired(res.data.message)) promptReauth()
    else ElMessage.error(res.data.message || '获取任务失败')
  } catch (e) {
    ElMessage.error('获取任务失败: ' + (e.response?.data?.message || e.message))
  } finally { tasksLoading.value = false }
}
// 状态排序优先级：进行中 > 未开始 > 已暂停 > 已完成；组内按计划开始时间倒序
const TASK_ST_ORDER = { '进行中': 0, '未开始': 1, '已暂停': 2, '已完成': 3 }
const TASK_ST_STYLE = {
  '进行中': { bg: '#e6f4ea', c: '#1a7f37' },
  '未开始': { bg: '#e8f0fe', c: '#1a56db' },
  '已暂停': { bg: '#fff4e0', c: '#9a6700' },
  '已完成': { bg: '#f0efe9', c: '#999' }
}
const taskStStyle = (st) => TASK_ST_STYLE[st] || { bg: '#f0efe9', c: '#999' }
const sortedTasks = computed(() => {
  return [...tasks.value].sort((a, b) => {
    const oa = TASK_ST_ORDER[a.rwZt] ?? 9, ob = TASK_ST_ORDER[b.rwZt] ?? 9
    if (oa !== ob) return oa - ob
    return (b.jhKsDate || '').localeCompare(a.jhKsDate || '')
  })
})
const ongoingCount = computed(() => tasks.value.filter(t => t.rwZt === '进行中').length)
// 任务分页
const taskStatusFilter = ref('')
const filteredTasks = computed(() =>
  taskStatusFilter.value ? sortedTasks.value.filter(t => t.rwZt === taskStatusFilter.value) : sortedTasks.value
)
const taskPage = ref(1)
const taskPageSize = ref(10)
const pagedTasks = computed(() => {
  const s = (taskPage.value - 1) * taskPageSize.value
  return filteredTasks.value.slice(s, s + taskPageSize.value)
})
watch(() => filteredTasks.value.length, () => { taskPage.value = 1 })

// ===== 配置 =====
const loadConfig = async () => {
  try {
    loading.value = true
    const res = await axios.get('/worktime-api/config')
    if (res.data.success && res.data.config) {
      config.value = {
        authorization: res.data.config.authorization || '',
        cookie: res.data.config.cookie || '',
        curl_template: res.data.config.curl_template || ''
      }
      canSubmit.value = !!res.data.can_submit
      tokenExp.value = res.data.token_exp || null
      if (config.value.curl_template) parseCurlCommand()
      activeTaskId.value = parsedInfo.value.template_data?.gstbRwId || ''
    }
  } catch (error) {
    if (error.response?.status !== 401) ElMessage.error('加载配置失败: ' + error.message)
  } finally { loading.value = false }
}

const parseCurlCommand = () => {
  // 每次重新解析前先清空，避免上一条 curl 的结果残留（粘新 curl 缺某字段时仍显示旧值/旧预览，造成误导）
  parsedInfo.value = { authorization: '', cookie: '', url: '', template_data: null, templateDataPreview: '' }
  if (!config.value.curl_template) return
  try {
    const s = config.value.curl_template
    parsedInfo.value.authorization = (s.match(/-H\s+'Authorization:\s*([^']+)'/) || [, ''])[1].trim()
    parsedInfo.value.cookie = (s.match(/-b\s+'([^']+)'/) || [, ''])[1].trim()
    parsedInfo.value.url = (s.match(/curl\s+'([^']+)'/) || [, ''])[1].trim()
    const dataMatch = s.match(/--data-raw\s+'({[\s\S]*?})'\s/)
    if (dataMatch) {
      parsedInfo.value.template_data = JSON.parse(dataMatch[1])
      parsedInfo.value.templateDataPreview = JSON.stringify({
        工作类型: parsedInfo.value.template_data.gstbGzlx,
        工作描述: parsedInfo.value.template_data.gstbGzbg,
        任务名称: parsedInfo.value.template_data.gstbRwmc,
        项目: parsedInfo.value.template_data.gstbSsxm
      }, null, 2)
    }
    if (parsedInfo.value.authorization && parsedInfo.value.cookie) ElMessage.success('自动识别成功')
  } catch (e) {
    ElMessage.warning('解析 curl 失败，请检查格式')
  }
}

const activeTaskId = ref('')   // 当前已保存配置对应的任务id，用于检测"换任务"

// 从 Authorization(JWT) 解析 user_id（前端用，base64url 解 payload）
const userIdFromToken = (auth) => {
  if (!auth) return ''
  let t = auth.trim()
  if (t.toLowerCase().startsWith('bearer ')) t = t.slice(7).trim()
  try {
    let p = t.split('.')[1]; if (!p) return ''
    p = p.replace(/-/g, '+').replace(/_/g, '/'); p += '='.repeat((4 - p.length % 4) % 4)
    return String(JSON.parse(decodeURIComponent(escape(atob(p)))).user_id || '')
  } catch { return '' }
}

// 换任务防呆(A+C)：同一用户、任务变了、且有待提交记录 → 提示「清空并切换 / 取消」。
// 返回 true=继续(可能已清空待提交)，false=取消切换。跨用户不处理(记录本就按 username 隔离)。
const confirmTaskSwitch = async (newUserId, newTaskId) => {
  const sameUser = newUserId && String(newUserId) === String(currentUser.value.username)
  if (!sameUser) return true
  if (!activeTaskId.value || !newTaskId || String(activeTaskId.value) === String(newTaskId)) return true
  if (todoCount.value === 0) return true
  try {
    await ElMessageBox.confirm(
      `你有 ${todoCount.value} 条待提交记录（属于当前任务）。\n换任务后，这些记录若提交会算到新任务名下。是否清空它们并切换？\n（想保留就点「取消」，先去「提交所选」）`,
      '切换任务', { confirmButtonText: '清空并切换', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return false }
  const ids = records.value.filter(r => r.status === 'pending' || r.status === 'failed').map(r => r.id)
  if (ids.length) { try { await axios.delete('/worktime-api/records', { data: { ids } }) } catch (e) {} }
  return true
}

// 保存配置到后端并建立身份（不导航）。供「保存配置」和「测试配置」复用。
// 返回 true=成功。测试必须先走这一步，否则后端没有 ?username/已存配置 → 查不到 → 测试假失败。
const persistConfig = async () => {
  const newTaskId = parsedInfo.value.template_data?.gstbRwId || ''
  const newUserId = userIdFromToken(parsedInfo.value.authorization || config.value.authorization)
  if (!await confirmTaskSwitch(newUserId, newTaskId)) return false
  const res = await axios.post('/worktime-api/config', config.value)
  if (!res.data.success) { ElMessage.error(res.data.message); return false }
  setUser(res.data.username, res.data.display_name)
  canSubmit.value = !!res.data.can_submit
  if (res.data.parsed) {
    parsedInfo.value = {
      ...res.data.parsed,
      templateDataPreview: res.data.parsed.template_data
        ? JSON.stringify({
            工作类型: res.data.parsed.template_data.gstbGzlx,
            工作描述: res.data.parsed.template_data.gstbGzbg,
            任务名称: res.data.parsed.template_data.gstbRwmc,
            项目: res.data.parsed.template_data.gstbSsxm
          }, null, 2)
        : ''
    }
  }
  activeTaskId.value = res.data.parsed?.template_data?.gstbRwId || newTaskId || ''
  return true
}

// 认证失效识别 + 统一提示（上游"登录过期"类）
const looksExpired = (msg) => /登录过期|登录失效|认证失效|未登录|token.*过期|过期.*登录/i.test(String(msg || ''))
const promptReauth = () => {
  ElMessageBox.alert(
    '认证已失效（token/cookie 过期，或被踢下线）。\n请重新登录 xiaokong.cfid.cn，按 F12 → Network 重新抓取 curl，回「认证配置」重新粘贴保存。',
    '认证失效，请重新抓取 curl',
    { confirmButtonText: '去认证配置', type: 'warning' }
  ).then(() => switchView('config')).catch(() => {})
}
// 保存后实测 token 是否还有效（用"我的任务"，它会明确返回"登录过期"）；失效→false。网络异常不误报。
const tokenAlive = async () => {
  try {
    const res = await axios.post('/worktime-api/my-tasks')
    if (res.data.success) { tasks.value = res.data.data || []; return true }
    return !looksExpired(res.data.message)
  } catch (e) { return true }
}

const saveConfig = async () => {
  try {
    loading.value = true
    if (!await persistConfig()) return
    ElMessage.success(`配置保存成功，当前用户：${currentUser.value.display_name}`)
    await loadRecords()
    qmap.value = {}
    if (!await tokenAlive()) { promptReauth(); return }   // token 失效→明确提示、留在配置页
    switchView('calendar')
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  } finally { loading.value = false }
}

// ===== 懒人模式：任意认证 + 选任务 =====
const configMode = ref('full')
const lazyEnabled = ref(false)
const lazyCurl = ref('')
const lazyTasks = ref([])
const lazyTaskId = ref('')
const lazyLoading = ref(false)
const lazyDisplayName = ref('')
const lazyLoadTasks = async () => {
  try {
    lazyLoading.value = true
    const res = await axios.post('/worktime-api/preview-tasks', { curl: lazyCurl.value })
    if (res.data.success) {
      lazyDisplayName.value = res.data.display_name || ''
      const all = res.data.data || []
      const ing = all.filter(t => t.rwZt === '进行中')
      lazyTasks.value = ing.length ? ing : all
      lazyTaskId.value = ''
      if (!ing.length) ElMessage.info(`没有进行中的任务，已列出全部 ${all.length} 个`)
      else ElMessage.success(`拉到 ${ing.length} 个进行中任务，选一个即可`)
    } else { ElMessage.error(res.data.message); lazyTasks.value = [] }
  } catch (e) {
    ElMessage.error('拉取失败: ' + (e.response?.data?.message || e.message))
  } finally { lazyLoading.value = false }
}
const saveLazyConfig = async () => {
  const task = lazyTasks.value.find(t => t.id === lazyTaskId.value)
  if (!task) return
  // 换任务防呆（同用户、有待提交时提示清空/取消）
  const lazyAuth = (lazyCurl.value.match(/-H\s+'Authorization:\s*([^']+)'/) || [, ''])[1]
  if (!await confirmTaskSwitch(userIdFromToken(lazyAuth), task.id)) return
  try {
    loading.value = true
    const res = await axios.post('/worktime-api/quick-config', { curl: lazyCurl.value, task })
    if (res.data.success) {
      setUser(res.data.username, res.data.display_name)
      activeTaskId.value = String(task.id)
      canSubmit.value = !!res.data.can_submit
      ElMessage.success(`配置完成！任务「${res.data.task_name}」，现在可以直接提交报工`)
      await loadConfig()
      await loadRecords()
      qmap.value = {}
      if (!await tokenAlive()) { promptReauth(); return }   // token 失效→明确提示、留在配置页
      switchView('calendar')
    } else ElMessage.error(res.data.message)
  } catch (e) {
    ElMessage.error('配置失败: ' + (e.response?.data?.message || e.message))
  } finally { loading.value = false }
}

const testConfig = async () => {
  try {
    loading.value = true
    if (!config.value.curl_template) { ElMessage.warning('请先粘贴 curl 再测试'); return }
    // 先保存以建立身份+落库（后端按已存配置去查上游，不先存就会"请先配置认证信息"假失败）
    if (!await persistConfig()) return
    const today = new Date().toISOString().split('T')[0]
    const res = await axios.post('/worktime-api/query-worktime', { start_date: today, end_date: today })
    const d0 = (res.data.data || [])[0]
    if (res.data.success && d0 && d0.status === 'success') ElMessage.success('配置已保存，测试成功，认证信息有效')
    else if (!res.data.success && looksExpired(res.data.message)) promptReauth()
    else if (d0 && d0.status !== 'success') promptReauth()   // getInitMsg 被拒(多半token失效)
    else ElMessage.error('配置测试失败: ' + (res.data.message || '上游返回异常'))
  } catch (error) {
    ElMessage.error('测试失败: ' + error.message)
  } finally { loading.value = false }
}


// ===== 可报工时日历 =====
const pad = (n) => String(n).padStart(2, '0')
const fmtDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

// 翻过的月份缓存在内存：一次会话内翻回来瞬时；刷新页面会清空、提交报工后主动失效
const monthCache = ref({})
const monthKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
const queryMonth = async (force = false) => {
  if (!requireUser()) return
  const d = calendarDate.value
  const key = monthKey(d)
  if (!force && monthCache.value[key]) {   // 命中缓存：瞬时，不再调后端
    qmap.value = monthCache.value[key]
    return
  }
  const first = fmtDate(new Date(d.getFullYear(), d.getMonth(), 1))
  const last = fmtDate(new Date(d.getFullYear(), d.getMonth() + 1, 0))
  try {
    queryLoading.value = true
    const res = await axios.post('/worktime-api/query-worktime', { start_date: first, end_date: last })
    if (res.data.success) {
      const map = {}
      for (const r of res.data.data) map[r.date] = r
      qmap.value = map
      monthCache.value[key] = map   // 存起来，翻回这个月就瞬时
    } else ElMessage.error(res.data.message)
  } catch (error) {
    ElMessage.error('查询失败: ' + error.message)
  } finally { queryLoading.value = false }
}

// 回到本月：已在本月则直接刷新，否则跳过去（跳转由 watch 触发重查）
const goToday = () => {
  const now = new Date()
  const d = calendarDate.value
  if (d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) queryMonth()
  else calendarDate.value = now
}

watch(calendarDate, (nv, ov) => {
  if (view.value !== 'calendar' || !currentUser.value.username) return
  if (nv.getFullYear() === ov.getFullYear() && nv.getMonth() === ov.getMonth()) return
  queryMonth()   // 翻月：命中缓存瞬时、否则查后端；已选的天跨月保留
})

// 日历选择：支持单击 + 按住鼠标拖动滑选（仅可填的天；跨月累加，记住当时工时）
const dayPickable = (data) => {
  if (data.type !== 'current-month') return false
  const r = qmap.value[data.day]
  if (!r || r.status !== 'success') return false
  return parseFloat(r.normal_hours || 0) + parseFloat(r.overtime_hours || 0) > 0
}
const applyDay = (data, select) => {
  if (!dayPickable(data)) return
  const r = qmap.value[data.day]
  if (select) selectedMap.value[data.day] = { normal_hours: r.normal_hours, overtime_hours: r.overtime_hours }
  else delete selectedMap.value[data.day]
}
const dragging = ref(false)
const dragSelect = ref(true)   // 由拖动起点决定：起点未选→这趟都选中，已选→这趟都取消
const startDrag = (data) => {
  if (!dayPickable(data)) return
  dragging.value = true
  dragSelect.value = !selectedMap.value[data.day]
  applyDay(data, dragSelect.value)
}
const dragOver = (data) => { if (dragging.value) applyDay(data, dragSelect.value) }
const endDrag = () => { dragging.value = false }
onMounted(() => window.addEventListener('mouseup', endDrag))
// 兼容旧引用：单击 = toggle
const toggleDay = (data) => applyDay(data, !selectedMap.value[data.day])

// 全选本月"正常工作日"里可填的天（跳过周末/节假日；合并进已选，不影响其它月份）
const selectAllFillable = () => {
  let added = 0
  for (const k in qmap.value) {
    const r = qmap.value[k]
    if (isBulkDay(k) && r.status === 'success' && (parseFloat(r.normal_hours || 0) + parseFloat(r.overtime_hours || 0)) > 0) {
      if (!selectedMap.value[k]) { selectedMap.value[k] = { normal_hours: r.normal_hours, overtime_hours: r.overtime_hours }; added++ }
    }
  }
  if (!added) ElMessage.info('本月没有新的可填工作日')
}

// 全选本周（今天所在周）可填的天，合并进已选
const selectThisWeek = () => {
  const today = new Date()
  const dow = today.getDay()                       // 0 周日 .. 6 周六
  const monday = new Date(today); monday.setDate(today.getDate() - ((dow + 6) % 7))
  const sunday = new Date(monday); sunday.setDate(monday.getDate() + 6)
  const lo = fmtDate(monday), hi = fmtDate(sunday)
  let added = 0
  for (const k in qmap.value) {
    if (k >= lo && k <= hi && isBulkDay(k)) {
      const r = qmap.value[k]
      if (r.status === 'success' && (parseFloat(r.normal_hours || 0) + parseFloat(r.overtime_hours || 0)) > 0) {
        if (!selectedMap.value[k]) { selectedMap.value[k] = { normal_hours: r.normal_hours, overtime_hours: r.overtime_hours }; added++ }
      }
    }
  }
  if (!added) ElMessage.info('本周没有可填的天（确认日历停在含本周的月份）')
}

const clearSel = () => { selectedMap.value = {} }

// 生成待填报：按每天可报工时写成 pending 草稿（不提交），跳到记录页供编辑
const generateDraft = async () => {
  if (!selectedCount.value) { ElMessage.warning('请先在日历上点选要填的天'); return }
  try {
    fillLoading.value = true
    const items = Object.entries(selectedMap.value).map(([date, h]) => ({
      date,
      normal_hours: h.normal_hours || 0,
      overtime_hours: h.overtime_hours || 0
    }))
    const res = await axios.post('/worktime-api/fill-draft', { items })
    if (res.data.success) {
      ElMessage.success(res.data.message)
      selectedMap.value = {}
      await loadRecords()
      view.value = 'records'   // 跳到记录页编辑后再提交
    } else {
      ElMessage.error(res.data.message)
    }
  } catch (error) {
    ElMessage.error('生成失败: ' + (error.response?.data?.message || error.message || error))
  } finally { fillLoading.value = false }
}

// 是否"正常工作日"（批量全选只挑这些）：法定节假日不算；调休补班算；周一~周五算
const isBulkDay = (d) => {
  if (HOLIDAYS[d]) return false
  if (MAKEUP_WORKDAYS[d]) return true
  const w = new Date(d).getDay()
  return w >= 1 && w <= 5
}
const dayHasFill = (d) => {
  const r = qmap.value[d]
  return !!(r && r.status === 'success' && (parseFloat(r.normal_hours || 0) + parseFloat(r.overtime_hours || 0)) > 0)
}
const cellClass = (data) => {
  if (data.type !== 'current-month') return 'is-other'
  const d = data.day
  const w = new Date(d).getDay()
  const isWeekend = (w === 0 || w === 6) && !MAKEUP_WORKDAYS[d]
  const isHol = !!HOLIDAYS[d]
  const has = dayHasFill(d)
  // 周末/节假日：有可填工时 → 可加班(橙、可手动点)，否则灰
  if (isHol || isWeekend) return has ? 'is-ot' : 'is-weekend'
  const row = qmap.value[d]
  if (!row) return ''
  if (row.status !== 'success') return 'is-err'
  return has ? 'is-has' : 'is-zero'
}

// ===== 记录 =====
const loadRecords = async () => {
  if (!currentUser.value.username) return
  try {
    loading.value = true
    const res = await axios.get('/worktime-api/records')
    if (res.data.success) { records.value = res.data.data; statistics.value = res.data.statistics }
  } catch (error) {
    if (error.response?.status !== 401) ElMessage.error('加载记录失败: ' + error.message)
  } finally { loading.value = false }
}

// 删除单条（仅删本地记录）
const deleteRow = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.date} 这条记录吗？\n仅删除本地记录，不影响已提交到原系统的数据。`,
      '删除记录', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await axios.delete('/worktime-api/records', { data: { ids: [row.id] } })
    if (res.data.success) { ElMessage.success(res.data.message); await loadRecords(); clearRecSel() }
    else ElMessage.error(res.data.message)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('删除失败: ' + (error.response?.data?.message || error.message))
  }
}

// 批量删除所选（仅删本地记录）
const deleteSelected = async () => {
  const ids = selectedRecords.value.map(r => r.id)
  if (!ids.length) { ElMessage.warning('请先勾选要删除的记录'); return }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${ids.length} 条记录吗？\n仅删除本地记录，不影响已提交到原系统的数据。`,
      '批量删除', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await axios.delete('/worktime-api/records', { data: { ids } })
    if (res.data.success) { ElMessage.success(res.data.message); await loadRecords(); clearRecSel() }
    else ElMessage.error(res.data.message)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('删除失败: ' + (error.response?.data?.message || error.message))
  }
}

// 列内编辑：改完即存（el-input-number 的 :max 已挡住超上限；后端再校验一次兜底）
const saveRow = async (row) => {
  try {
    const res = await axios.put('/worktime-api/records', {
      id: row.id, normal_hours: row.normal_hours, overtime_hours: row.overtime_hours, work_content: row.work_content || ''
    })
    if (!res.data.success) { ElMessage.error(res.data.message); await loadRecords() }
  } catch (error) {
    ElMessage.error('保存失败: ' + (error.response?.data?.message || error.message))
    await loadRecords()
  }
}

// 批量改整列（作用于当前筛选出的记录）
const applyBatch = async (field) => {
  const ids = filteredRecords.value.map(r => r.id)
  if (!ids.length) { ElMessage.warning('当前没有记录'); return }
  const label = { normal: '正常工时', overtime: '加班工时', content: '工作内容' }[field]
  const value = field === 'content' ? batch.value.content : (field === 'normal' ? batch.value.normal : batch.value.overtime)
  try {
    await ElMessageBox.confirm(
      field === 'content'
        ? `把当前 ${ids.length} 条的「工作内容」都设为：${value || '(空)'}？`
        : `把当前 ${ids.length} 条的「${label}」都设为 ${value}？（每天会按各自「可填上限」自动封顶）`,
      '批量设置', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await axios.post('/worktime-api/records/batch', { field, value, ids })
    if (res.data.success) { ElMessage.success(res.data.message); await loadRecords() }
    else ElMessage.error(res.data.message)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('批量设置失败: ' + (error.response?.data?.message || error.message))
  }
}

const handleSelectionChange = (sel) => { selectedRecords.value = sel }
// 跨页全选：对全部 filteredRecords 逐行勾选；配合 el-table reserve-selection 跨页保留
const selectAllTodo = () => {
  filteredRecords.value.forEach(r => recTable.value?.toggleRowSelection(r, true))
}
const clearRecSel = () => {
  recTable.value?.clearSelection()
  selectedRecords.value = []
}

const SUBMIT_CONCURRENCY = 5   // 前端并发上限（与后端 Semaphore 一致）

const submitSelectedRecords = async () => {
  if (selectedRecords.value.length === 0) { ElMessage.warning('请选择要提交的记录'); return }
  // 软拦截：报工日期超出任务计划周期的，提交前显式确认（仍允许提交）
  const oor = selectedRecords.value.filter(r => isOutOfRange(r.date))
  let confirmMsg = `确定提交选中的 ${selectedRecords.value.length} 条记录吗？`
  if (oor.length) {
    const { ks, js } = taskPeriod.value
    const dates = oor.map(r => r.date).sort()
    const shown = dates.slice(0, 12).join('、') + (dates.length > 12 ? ` 等 ${dates.length} 个` : '')
    confirmMsg = `<p>⚠ 有 <b>${oor.length}</b> 条报工日期超出任务计划周期（${ks} ~ ${js}）：</p>`
      + `<p style="color:#d9534f;margin:6px 0">${shown}</p>`
      + `<p>这些日期理论上不在该任务范围内，确定仍要提交吗？</p>`
  }
  try {
    await ElMessageBox.confirm(confirmMsg, '确认提交', {
      confirmButtonText: oor.length ? '仍要提交' : '确定', cancelButtonText: '取消',
      type: oor.length ? 'warning' : 'info', dangerouslyUseHTMLString: !!oor.length
    })
  } catch { return }   // 取消

  // 快照所选，逐条并发提交（每条单独调 /submit，实时知道提交到哪条）
  const targets = [...selectedRecords.value]
  submitItems.value = targets.map(r => ({ id: r.id, date: r.date, state: 'wait', error: '' }))
  submitting.value = true
  loading.value = true
  try {
    let idx = 0
    const worker = async () => {
      while (idx < targets.length) {
        const i = idx++
        const rec = targets[i], item = submitItems.value[i]
        item.state = 'doing'
        try {
          const res = await axios.post('/worktime-api/submit', { record_ids: [rec.id] })
          const r0 = (res.data.data || [])[0]
          if (res.data.success && r0 && r0.status === 'success') {
            item.state = 'ok'
          } else {
            item.state = 'fail'
            item.error = (r0 && r0.error) || res.data.message || '提交失败'
          }
        } catch (e) {
          item.state = 'fail'
          item.error = e.response?.data?.message || e.message || String(e)
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(SUBMIT_CONCURRENCY, targets.length) }, worker))

    const ok = submitOk.value, fail = submitFail.value
    submitting.value = false
    if (fail === 0) {
      ElMessage.success(`全部提交成功，共 ${ok} 条`)
    } else {
      const detail = submitItems.value.filter(i => i.state === 'fail').slice(0, 12)
        .map(i => `· ${i.date || i.id}：${i.error || '失败'}`).join('\n')
      ElMessageBox.alert(`成功 ${ok} 条，失败 ${fail} 条：\n\n${detail}`, '提交结果', { type: 'warning' })
    }
    await loadRecords()
    clearRecSel()   // 已提交的记录离开待处理列表，清掉勾选避免残留计数
    monthCache.value = {}; qmap.value = {}   // 提交改了可报工时：清缓存+当前显示，回日历会重查到最新
  } catch (error) {
    ElMessage.error('提交失败: ' + (error.message || error))
  } finally { submitting.value = false; loading.value = false }
}

// ===== 工具 =====
const requireUser = () => {
  if (!currentUser.value.username) { ElMessage.warning('请先完成认证配置'); view.value = 'config'; return false }
  return true
}
const getWeekdayName = (d) => ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(d).getDay()]
const weekendTag = (d) => { const w = new Date(d).getDay(); return (w === 0 || w === 6) ? 'tag-orange' : 'tag-neutral' }
const statusTag = (s) => ({ submitted: 'tag-green', failed: 'tag-red', pending: 'tag-gray' }[s] || 'tag-gray')
const holidayName = (d) => HOLIDAYS[d] || ''
const isMakeup = (d) => !!MAKEUP_WORKDAYS[d]

// 登录后/带令牌时加载用户态
const bootstrap = async () => {
  const saved = localStorage.getItem('worktime_user')
  if (saved) {
    try {
      const u = JSON.parse(saved)
      if (u && u.username) {
        currentUser.value = u
        await loadConfig()
        await loadRecords()
        view.value = 'calendar'
        queryMonth()
        return
      }
    } catch (e) { /* ignore */ }
  }
  view.value = 'config'
}

onMounted(() => { if (accessToken.value) bootstrap() })
</script>

<!-- ===== 全局主题：Claude 暖色 + Element Plus 覆盖 ===== -->
<style>
:root {
  --el-color-primary: #d97757;
  --el-color-primary-light-3: #e0937a;
  --el-color-primary-light-5: #e7af9c;
  --el-color-primary-light-7: #eeccbe;
  --el-color-primary-light-8: #f2dacf;
  --el-color-primary-light-9: #fbf0eb;
  --el-color-primary-dark-2: #c15f3c;
  --el-color-success: #5b9c6a;
  --el-color-warning: #d9883b;
  --el-color-danger: #c24a3c;
  --el-color-error: #c24a3c;
  --el-border-radius-base: 8px;
  --el-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --el-text-color-primary: #1f1e1d;
}
* { box-sizing: border-box; }
body { margin: 0; background: #f4f2ec; color: #1f1e1d; font-family: var(--el-font-family); }

.el-table th.el-table__cell { background: #faf8f3 !important; color: #6b6a64; font-weight: 600; }
.el-table { --el-table-border-color: #ece9e0; --el-table-row-hover-bg-color: #faf8f3; font-size: 13px; }
.el-calendar { --el-calendar-cell-width: 90px; background: transparent; }
.el-calendar__header { padding: 4px 0 14px; border-bottom: none; }
.el-calendar-table thead th { color: #a8a59c; font-weight: 600; }
.el-calendar-table td { border-color: #ece9e0 !important; }
.el-calendar-table td.is-today .cal-day { color: #c15f3c; font-weight: 700; }
.el-calendar-table td.is-selected { background: transparent; }
</style>

<!-- ===== 布局（scoped） ===== -->
<style scoped>
/* 登录 */
.login-wrap {
  min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px;
  background:
    radial-gradient(1200px 600px at 50% -10%, #fbeee7 0%, transparent 60%),
    radial-gradient(900px 500px at 90% 110%, #f3e6dc 0%, transparent 55%),
    #f4f2ec;
}
.login-card {
  width: 360px; background: #fffdfa; border: 1px solid #ece6db; border-radius: 16px;
  padding: 32px 28px; box-shadow: 0 12px 40px rgba(120, 80, 50, .12);
}
.login-brand { display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 700; color: #1f1e1d; }
.login-sub { margin: 6px 0 22px; color: #8a877e; font-size: 13px; }
.login-field { margin-bottom: 14px; }
.login-field label { display: block; font-size: 13px; color: #6b6a64; margin-bottom: 6px; }
.login-field input {
  width: 100%; padding: 10px 12px; border: 1px solid #ddd7cb; border-radius: 8px; font-size: 14px;
  background: #fff; color: #1f1e1d; transition: all .2s;
}
.login-field input:focus { outline: none; border-color: #d97757; box-shadow: 0 0 0 3px rgba(217,119,87,.15); }
.login-btn { width: 100%; justify-content: center; margin-top: 8px; padding: 11px; font-size: 15px; }
.login-foot { color: #a8a59c; font-size: 12px; }

.layout { display: flex; min-height: 100vh; }

/* 侧边栏（暖炭） */
.sidebar { width: 220px; flex-shrink: 0; background: #2b2926; color: #fff; display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 10px; padding: 20px 20px 18px; font-size: 17px; font-weight: 700; letter-spacing: .5px; border-bottom: 1px solid #3a3733; }
.brand-dot { width: 10px; height: 10px; border-radius: 50%; background: #d97757; box-shadow: 0 0 0 4px rgba(217,119,87,.22); }
.nav { padding: 10px 0; flex: 1; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 12px 20px; color: rgba(255,255,255,.64); cursor: pointer; transition: all .2s; font-size: 14px; border-left: 3px solid transparent; }
.nav-item:hover { color: #fff; background: #353230; }
.nav-item.active { color: #fff; background: linear-gradient(90deg, rgba(217,119,87,.24), transparent); border-left-color: #d97757; }
.nav-ico { font-size: 16px; }
.nav-badge { margin-left: auto; background: #d97757; color: #fff; font-size: 11px; padding: 0 7px; border-radius: 10px; line-height: 18px; }
.side-user { padding: 14px 16px; border-top: 1px solid #3a3733; display: flex; align-items: center; gap: 10px; }
.su-avatar { width: 34px; height: 34px; border-radius: 50%; background: #d97757; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; }
.su-meta { flex: 1; min-width: 0; }
.su-name { font-size: 14px; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.su-id { font-size: 11px; color: #8fc79b; }
.su-logout { background: none; border: none; color: rgba(255,255,255,.5); cursor: pointer; font-size: 18px; }
.su-logout:hover { color: #e7886c; }
.su-empty { font-size: 12px; color: rgba(255,255,255,.4); flex: 1; }

/* 内容区 */
.content { flex: 1; padding: 24px 28px; overflow-y: auto; }
.page-head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 18px; gap: 12px; flex-wrap: wrap; }
.page-head h2 { margin: 0; font-size: 21px; font-weight: 700; color: #1f1e1d; }
.sub { margin: 4px 0 0; font-size: 13px; color: #8a877e; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

.card { background: #fffdfa; border: 1px solid #ece6db; border-radius: 12px; padding: 18px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(60,40,20,.04); }
.card.empty { text-align: center; color: #a8a59c; padding: 48px; }
.toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.tb-label { font-size: 13px; color: #6b6a64; }
.tb-divider { width: 1px; height: 22px; background: #ece6db; margin: 0 4px; }
.tb-count { font-size: 13px; color: #8a877e; margin-left: 4px; }
.tb-hint { font-size: 12px; color: #a8a59c; }
.batch-bar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.bb-item { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #44423d; }
.cap-hint { font-size: 12px; color: #8a877e; }
.hint { color: #a8a59c; font-size: 12px; margin: 4px 2px; }
.inline-hint { margin-left: 10px; color: #a8a59c; font-size: 13px; }

/* 按钮 */
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 7px 15px; border: 1px solid #ddd7cb; border-radius: 8px; background: #fffdfa; color: #44423d; cursor: pointer; font-size: 13px; transition: all .2s; }
.btn:hover { border-color: #d97757; color: #c15f3c; }
.btn-primary { background: #d97757; color: #fff; border-color: #d97757; }
.btn-primary:hover { background: #c96442; border-color: #c96442; color: #fff; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn:disabled:hover { border-color: #ddd7cb; color: #44423d; }
.btn-danger { background: #fff; color: #b0432f; border-color: #eab4a6; }
.btn-danger:hover { background: #c24a3c; color: #fff; border-color: #c24a3c; }
.btn-danger:disabled:hover { background: #fff; color: #b0432f; border-color: #eab4a6; }
.link { color: #c15f3c; cursor: pointer; font-size: 13px; }
.link:hover { color: #d97757; }
.link.danger { color: #b0432f; }
.link.danger:hover { color: #c24a3c; }

/* 标签 */
.tag { display: inline-block; padding: 1px 9px; border-radius: 6px; font-size: 12px; line-height: 18px; }
.tag-red { background: #fbeae6; color: #b0432f; border: 1px solid #eecabd; }
.tag-orange { background: #fbeede; color: #b06a2d; border: 1px solid #f0d7b9; }
.tag-green { background: #eaf2e8; color: #4a7a4a; border: 1px solid #cde0c8; }
.tag-gray { background: #f1efe7; color: #8a877e; border: 1px solid #e3ded2; }
.tag-neutral { background: #f3efe7; color: #7a776e; border: 1px solid #e6e0d3; }

/* 统计卡 */
.sum-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px; }
.sum-grid.five { grid-template-columns: repeat(5, 1fr); }
.sum-card { background: #fffdfa; border: 1px solid #ece6db; border-radius: 12px; padding: 16px 18px; box-shadow: 0 1px 2px rgba(60,40,20,.04); border-left: 3px solid #d97757; }
.sum-label { font-size: 12px; color: #8a877e; }
.sum-num { font-size: 26px; font-weight: 700; color: #1f1e1d; margin-top: 4px; }

/* 表单 */
.form-group { margin-bottom: 16px; }
.form-label { display: block; margin-bottom: 6px; font-size: 13px; color: #6b6a64; font-weight: 600; }
.form-hint { font-size: 12px; color: #8a877e; margin: 8px 0 0; line-height: 1.9; }
.form-hint b { color: #c15f3c; font-weight: 600; }
.hint-tip { display: inline-block; margin-top: 6px; padding: 6px 10px; background: #f7f4ee; border-left: 3px solid #d97757; border-radius: 4px; color: #6b6a64; }
.form-actions { display: flex; gap: 10px; margin-top: 4px; }
.parsed-grid { display: flex; gap: 24px; flex-wrap: wrap; margin: 4px 0 14px; }
.parsed-item { display: flex; align-items: center; gap: 8px; }
.pi-label { font-size: 13px; color: #6b6a64; }
.code-pre { background: #f7f4ee; border: 1px solid #ece6db; border-radius: 8px; padding: 12px; font-size: 12px; color: #6b6a64; overflow: auto; margin: 0; }

/* 填报工具条 / 提示 */
.warn-banner { background: #fbeede; border: 1px solid #f0d7b9; border-left: 3px solid #d9883b; color: #9a5a1f; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; font-size: 13px; }
.warn-banner b { color: #b06a2d; }
.fill-bar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; padding-bottom: 12px; margin-bottom: 4px; border-bottom: 1px dashed #ece6db; }
.fb-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.fb-tip { color: #8a877e; font-size: 13px; }
.fb-sel { font-size: 13px; color: #44423d; }
.fb-sel b { color: #c15f3c; }
.fb-right { display: flex; gap: 8px; }

/* 日历 */
.cal-card { padding: 14px 18px 6px; }
.legend { display: flex; gap: 18px; margin-bottom: 6px; font-size: 12px; color: #6b6a64; }
.legend .dot { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.dot.has { background: #b6d4ab; } .dot.zero { background: #e3ded2; } .dot.err { background: #eab4a6; } .dot.weekend { background: #f3efe7; border: 1px solid #e3ded2; } .dot.sel { background: #fff; border: 2px solid #d97757; } .dot.ot { background: #f7d9bb; }
.cal-cell { height: 100%; min-height: 56px; display: flex; flex-direction: column; padding: 4px 6px; border-radius: 8px; transition: all .15s; border: 2px solid transparent; }
.cal-cell.sel { border-color: #d97757; background: #fbeee7 !important; box-shadow: 0 0 0 1px rgba(217,119,87,.25) inset; }
.sel-check { color: #d97757; font-weight: 700; margin-left: 2px; }
.cal-badge { float: right; font-size: 10px; line-height: 15px; padding: 0 5px; border-radius: 8px; font-weight: 600; }
.cal-badge.hol { background: #fbeae6; color: #b0432f; border: 1px solid #eecabd; }
.cal-badge.mk { background: #fbeede; color: #b06a2d; border: 1px solid #f0d7b9; }
.lg-badge { display: inline-block; font-size: 10px; line-height: 15px; padding: 0 5px; border-radius: 8px; font-weight: 600; margin-left: 6px; }
.lg-badge.hol { background: #fbeae6; color: #b0432f; border: 1px solid #eecabd; }
.lg-badge.mk { background: #fbeede; color: #b06a2d; border: 1px solid #f0d7b9; }
.cal-day { font-size: 13px; font-weight: 600; color: #6b6a64; }
.cal-hours { margin-top: 3px; display: flex; flex-direction: column; gap: 1px; font-size: 12px; }
.ch-n { color: #4a7a4a; font-weight: 600; }
.ch-o { color: #b06a2d; }
.ch-err { color: #b0432f; font-size: 12px; }
.cal-cell.is-has { background: #eef5ea; cursor: pointer; }
.cal-cell.is-has:hover { background: #e3f0db; }
.cal-cell.is-ot { background: #fdf3e9; cursor: pointer; }
.cal-cell.is-ot:hover { background: #f9e8d6; }
.cal-cell.is-zero { background: #f6f4ee; }
.cal-cell.is-zero .cal-day { color: #b8b4a9; }
.cal-cell.is-err { background: #fbeae6; }
.cal-cell.is-weekend { background: #f7f5ef; }
.cal-cell.is-weekend .cal-day { color: #c2bdb0; }
.cal-cell.is-other { opacity: .35; }

.spinner { display: inline-block; width: 13px; height: 13px; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin .6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 提交进度弹窗 */
.submit-prog .sp-stat { margin: 12px 0 8px; font-size: 13px; color: #555; }
.submit-prog .sp-list { list-style: none; margin: 0; padding: 0; max-height: 240px; overflow-y: auto; border: 1px solid #eee; border-radius: 6px; }
.submit-prog .sp-list li { display: flex; align-items: center; gap: 8px; padding: 6px 10px; font-size: 13px; border-bottom: 1px solid #f5f5f5; }
.submit-prog .sp-list li:last-child { border-bottom: none; }
.submit-prog .sp-ico { width: 16px; text-align: center; flex: none; }
.submit-prog .sp-date { font-variant-numeric: tabular-nums; }
.submit-prog .sp-err { color: #d9534f; font-size: 12px; margin-left: auto; }
.submit-prog .sp-ok .sp-ico { color: #2e9b54; }
.submit-prog .sp-fail .sp-ico { color: #d9534f; }
.submit-prog .sp-doing { background: #f6f9ff; }
.submit-prog .sp-wait { color: #999; }
.submit-prog .sp-tip { margin: 10px 0 0; font-size: 12px; color: #aaa; }

/* 本次报工任务信息条 */
.report-task-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.report-task-bar .rt-label { font-weight: 600; color: #333; }
.report-task-bar .rt-name { font-weight: 600; color: #d97757; }
.report-task-bar .rt-item { font-size: 13px; color: #666; }
.report-task-bar .rt-tip { font-size: 12px; color: #bbb; }
</style>
