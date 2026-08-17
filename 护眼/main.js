// 动画参数
let animationConfig = {
    shape: 'circle', // 点的形状
    color: '#145A32', // 墨绿色，护眼
    size: 24, // 点的大小
    speed: 2, // 移动速度（像素/帧）
    path: 'circle', // 轨迹类型
};

// 统计数据
let stats = {
    eyeExerciseTime: 0, // 用眼时长（分钟）
    restCount: 0, // 休息次数
    followCount: 0, // 跟随训练次数
};

// 新增训练模式参数
let trainingConfig = {
    mode: 'single', // 训练模式: single, multi, eight, nearfar
    multiCount: 3,  // 多点数量
    nearfarInterval: 2, // 远近交替间隔（秒）
};

// 初始化
window.onload = function() {
    // 设置区展开/收起逻辑
    const settingsToggle = document.getElementById('settings-toggle');
    const settingsArea = document.getElementById('settings-area');
    const settingsClose = document.getElementById('settings-close');
    settingsToggle.onclick = function() {
        settingsArea.style.display = '';
        settingsToggle.style.display = 'none';
    };
    settingsClose.onclick = function() {
        settingsArea.style.display = 'none';
        settingsToggle.style.display = '';
    };
    // 初始化动画区域
    initAnimationArea();
    // 初始化参数设置
    initSettingsArea();
    // 初始化数据统计
    updateStatsArea();
    // 初始化护眼计时器
    initEyeTimer();
    // 初始化护眼统计框
    initEyeStatsBox();
};

function initAnimationArea() {
    const canvas = document.getElementById('eye-canvas');
    const ctx = canvas.getContext('2d');

    // 动态调整canvas尺寸为全屏
    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    function getCenterAndRadius() {
        const w = window.innerWidth;
        const h = window.innerHeight;
        // 轨迹中心点上移，避开底部设置区
        const centerX = w / 2;
        const centerY = h * 0.35;
        // 横向最大，纵向半径避开底部
        const radius = Math.min(w * 0.45, (h * 0.35) - animationConfig.size - 20);
        return {centerX, centerY, radius, w, h};
    }

    // 多点参数
    let multiAngles = [];
    function resetMultiAngles() {
        multiAngles = [];
        for (let i = 0; i < trainingConfig.multiCount; i++) {
            multiAngles.push((2 * Math.PI / trainingConfig.multiCount) * i);
        }
    }
    resetMultiAngles();

    // 远近交替参数
    let nearfarState = 'near';
    let nearfarTimer = 0;
    let lastSwitch = Date.now();

    let angle = 0;
    let t = 0;

    function draw() {
        const {centerX, centerY, radius, w, h} = getCenterAndRadius();
        ctx.clearRect(0, 0, w, h);
        if (trainingConfig.mode === 'single') {
            // 单点跟随，支持三种轨迹
            let x, y;
            if (animationConfig.path === 'circle') {
                x = centerX + radius * Math.cos(angle);
                y = centerY + radius * Math.sin(angle);
            } else if (animationConfig.path === 'eight') {
                x = centerX + radius * Math.sin(angle);
                y = centerY + radius * Math.sin(angle) * Math.cos(angle);
            } else if (animationConfig.path === 'random') {
                if (!draw.target || t >= 1) {
                    draw.start = draw.target || {x: centerX, y: centerY};
                    draw.target = {
                        x: Math.random() * (w - 2 * animationConfig.size) + animationConfig.size,
                        y: Math.random() * (h - 2 * animationConfig.size) + animationConfig.size
                    };
                    const dx = draw.target.x - draw.start.x;
                    const dy = draw.target.y - draw.start.y;
                    draw.distance = Math.sqrt(dx*dx + dy*dy);
                    t = 0;
                }
                t += animationConfig.speed / (draw.distance || 1);
                if (t > 1) t = 1;
                x = draw.start.x + (draw.target.x - draw.start.x) * t;
                y = draw.start.y + (draw.target.y - draw.start.y) * t;
            }
            ctx.beginPath();
            ctx.arc(x, y, animationConfig.size, 0, 2 * Math.PI);
            ctx.fillStyle = animationConfig.color;
            ctx.shadowColor = animationConfig.color;
            ctx.shadowBlur = 8;
            ctx.fill();
            ctx.closePath();
            ctx.shadowBlur = 0;
        } else if (trainingConfig.mode === 'multi') {
            // 多点跟随，均匀分布在圆形轨迹
            for (let i = 0; i < trainingConfig.multiCount; i++) {
                let a = angle + multiAngles[i];
                let x = centerX + radius * Math.cos(a);
                let y = centerY + radius * Math.sin(a);
                ctx.beginPath();
                ctx.arc(x, y, animationConfig.size, 0, 2 * Math.PI);
                ctx.fillStyle = animationConfig.color;
                ctx.shadowColor = animationConfig.color;
                ctx.shadowBlur = 8;
                ctx.fill();
                ctx.closePath();
                ctx.shadowBlur = 0;
            }
        } else if (trainingConfig.mode === 'eight') {
            // 八字形轨迹（多点）
            for (let i = 0; i < trainingConfig.multiCount; i++) {
                let a = angle + multiAngles[i];
                let x = centerX + radius * Math.sin(a);
                let y = centerY + radius * Math.sin(a) * Math.cos(a);
                ctx.beginPath();
                ctx.arc(x, y, animationConfig.size, 0, 2 * Math.PI);
                ctx.fillStyle = animationConfig.color;
                ctx.shadowColor = animationConfig.color;
                ctx.shadowBlur = 8;
                ctx.fill();
                ctx.closePath();
                ctx.shadowBlur = 0;
            }
        } else if (trainingConfig.mode === 'nearfar') {
            // 远近交替（米字型分布，防止连续重复）
            let now = Date.now();
            if (now - lastSwitch > trainingConfig.nearfarInterval * 1000) {
                nearfarState = nearfarState === 'near' ? 'far' : 'near';
                lastSwitch = now;
                if (nearfarState === 'far') {
                    // 切换到远时，随机选一个与上次不同的方向
                    const margin = animationConfig.size * 2;
                    const farPointsCount = 8;
                    let idx;
                    do {
                        idx = Math.floor(Math.random() * farPointsCount);
                    } while (draw.farIdx === idx && farPointsCount > 1);
                    draw.farIdx = idx;
                }
            }
            let x, y, r;
            if (nearfarState === 'near') {
                x = centerX;
                y = centerY;
                r = animationConfig.size * 2.2;
            } else {
                // 米字型八个方向
                const margin = animationConfig.size * 2;
                const farPoints = [
                    {x: centerX, y: margin},
                    {x: centerX, y: h - margin},
                    {x: margin, y: centerY},
                    {x: w - margin, y: centerY},
                    {x: margin, y: margin},
                    {x: w - margin, y: margin},
                    {x: margin, y: h - margin},
                    {x: w - margin, y: h - margin}
                ];
                // 初始时随机一个方向
                if (typeof draw.farIdx !== 'number') {
                    draw.farIdx = Math.floor(Math.random() * farPoints.length);
                }
                x = farPoints[draw.farIdx].x;
                y = farPoints[draw.farIdx].y;
                r = animationConfig.size * 1.2;
            }
            ctx.beginPath();
            ctx.arc(x, y, r, 0, 2 * Math.PI);
            ctx.fillStyle = nearfarState === 'near' ? '#145A32' : '#FFA940';
            ctx.shadowColor = ctx.fillStyle;
            ctx.shadowBlur = 12;
            ctx.fill();
            ctx.closePath();
            ctx.shadowBlur = 0;
        }
        // 更新角度/进度
        if (trainingConfig.mode === 'single' || trainingConfig.mode === 'multi' || trainingConfig.mode === 'eight') {
            angle += animationConfig.speed * 0.01;
            if (angle > 2 * Math.PI) angle -= 2 * Math.PI;
        }
        requestAnimationFrame(draw);
    }
    draw();

    // 监听多点数量变化
    window.resetMultiAngles = resetMultiAngles;
}

function initSettingsArea() {
    // 训练模式切换
    const modeSelect = document.getElementById('mode-select');
    const multiSettings = document.getElementById('multi-settings');
    const nearfarSettings = document.getElementById('nearfar-settings');
    modeSelect.value = trainingConfig.mode;
    function updateModeUI() {
        multiSettings.style.display = (modeSelect.value === 'multi' || modeSelect.value === 'eight') ? '' : 'none';
        nearfarSettings.style.display = (modeSelect.value === 'nearfar') ? '' : 'none';
    }
    modeSelect.onchange = function() {
        trainingConfig.mode = this.value;
        updateModeUI();
        if (this.value === 'multi' || this.value === 'eight') {
            window.resetMultiAngles();
        }
    };
    updateModeUI();
    // 多点数量
    const multiCount = document.getElementById('multi-count');
    multiCount.value = trainingConfig.multiCount;
    multiCount.oninput = function() {
        trainingConfig.multiCount = parseInt(this.value);
        window.resetMultiAngles();
    };
    // 远近交替间隔
    const nearfarInterval = document.getElementById('nearfar-interval');
    nearfarInterval.value = trainingConfig.nearfarInterval;
    nearfarInterval.oninput = function() {
        trainingConfig.nearfarInterval = parseFloat(this.value);
    };
    // 速度滑块
    const speedRange = document.getElementById('speed-range');
    const speedValue = document.getElementById('speed-value');
    speedRange.value = animationConfig.speed;
    speedValue.textContent = animationConfig.speed;
    speedRange.oninput = function() {
        animationConfig.speed = parseFloat(this.value);
        speedValue.textContent = this.value;
    };
    // 轨迹选择
    const pathSelect = document.getElementById('path-select');
    pathSelect.value = animationConfig.path;
    pathSelect.onchange = function() {
        animationConfig.path = this.value;
    };
    // 点大小滑块
    const sizeRange = document.getElementById('size-range');
    const sizeValue = document.getElementById('size-value');
    sizeRange.value = animationConfig.size;
    sizeValue.textContent = animationConfig.size;
    sizeRange.oninput = function() {
        animationConfig.size = parseInt(this.value);
        sizeValue.textContent = this.value;
    };
}

function updateStatsArea() {
    // 后续实现数据统计展示
}

// ====== 护眼计时功能 ======
function initEyeTimer() {
    const timerDisplay = document.getElementById('timer-display');
    const timerBtn = document.getElementById('timer-btn');
    let timer = null;
    let startTime = null;
    let elapsed = 0; // 当前轮累计秒数（未满1分钟）
    let running = false;
    let totalSec = 0; // 本次计时总秒数
    let autoCount = 0; // 本次自动打卡次数

    function formatTime(sec) {
        const h = String(Math.floor(sec/3600)).padStart(2,'0');
        const m = String(Math.floor((sec%3600)/60)).padStart(2,'0');
        const s = String(sec%60).padStart(2,'0');
        return `${h}:${m}:${s}`;
    }
    function updateDisplay() {
        let showSec = totalSec;
        if (running && startTime) {
            showSec = totalSec + Math.floor((Date.now() - startTime)/1000);
        }
        timerDisplay.textContent = '护眼时长：' + formatTime(showSec);
    }
    function writeAutoRecordSignal(totalSec) {
        if (totalSec < 60) return;
        const params = new URLSearchParams(window.location.search);
        const recordUrl = params.get('autorecord');
        if (!recordUrl) return;
        fetch(recordUrl, {
            method: 'POST',
            headers: {'Content-Type': 'text/plain;charset=UTF-8'},
            body: String(totalSec)
        }).catch(function() {});
    }
    function autoRecord() {
        // 记录1分钟
        let arr = JSON.parse(localStorage.getItem('eyeTimeRecords')||'[]');
        arr.push({ts: Date.now(), sec: 60});
        localStorage.setItem('eyeTimeRecords', JSON.stringify(arr));
        updateEyeStatsBox();
        autoCount += 1;
        // 删除写同步文件的部分
    }
    function startTimer() {
        if (running) return;
        running = true;
        startTime = Date.now();
        timerBtn.textContent = '结束计时';
        timerBtn.style.background = '#e57373';
        timer = setInterval(() => {
            let now = Date.now();
            let sec = Math.floor((now - startTime)/1000);
            // 检查是否满1分钟
            if (sec + elapsed >= 60) {
                // 只处理满的分钟数
                let fullMin = Math.floor((sec + elapsed) / 60);
                for (let i = 0; i < fullMin; i++) {
                    autoRecord();
                }
                // 剩余秒数
                elapsed = (sec + elapsed) % 60;
                // 更新时间基点
                startTime = now - (elapsed * 1000);
                totalSec += fullMin * 60;
            }
            updateDisplay();
        }, 1000);
        updateDisplay();
    }
    function stopTimer() {
        if (!running) return;
        running = false;
        let now = Date.now();
        let sec = Math.floor((now - startTime)/1000);
        totalSec += sec;
        clearInterval(timer);
        timer = null;
        timerBtn.textContent = '开始计时';
        timerBtn.style.background = '#4caf50';
        updateDisplay();
        alert('本次护眼总时长：' + formatTime(totalSec));
        writeAutoRecordSignal(totalSec);
        // 新增：通过pywebview api自动同步到主程序
        if (window.pywebview && window.pywebview.api && window.pywebview.api.record_eye) {
            window.pywebview.api.record_eye(totalSec).then(function(resp) {
                // 可选：同步成功提示
            });
        }
        // 重置
        elapsed = 0;
        totalSec = 0;
        autoCount = 0;
        updateDisplay();
    }
    timerBtn.onclick = function() {
        if (!running) {
            startTimer();
        } else {
            stopTimer();
        }
    };
    updateDisplay();
}
// ====== 护眼统计框功能 ======
function initEyeStatsBox() {
    const box = document.getElementById('eye-stats-box');
    const content = document.getElementById('eye-stats-content');
    const toggleBtn = document.getElementById('eye-stats-toggle');
    let expanded = true;
    toggleBtn.onclick = function() {
        expanded = !expanded;
        if (expanded) {
            content.style.display = '';
            toggleBtn.textContent = '－';
            box.style.minHeight = '';
            box.style.height = '';
        } else {
            content.style.display = 'none';
            toggleBtn.textContent = '＋';
            box.style.minHeight = '0';
            box.style.height = '36px';
        }
    };
    updateEyeStatsBox();
}
function updateEyeStatsBox() {
    const content = document.getElementById('eye-stats-content');
    if (!content) return;
    let arr = JSON.parse(localStorage.getItem('eyeTimeRecords')||'[]');
    let totalSec = arr.reduce((s, r) => s + (r.sec||0), 0);
    let totalCnt = arr.length;
    function formatTime(sec) {
        const h = String(Math.floor(sec/3600)).padStart(2,'0');
        const m = String(Math.floor((sec%3600)/60)).padStart(2,'0');
        const s = String(sec%60).padStart(2,'0');
        return `${h}:${m}:${s}`;
    }
    let html = `<div style='color:#145A32;font-size:1.1em;'>累计护眼：<b>${totalCnt}</b> 次<br>总时长：<b>${formatTime(totalSec)}</b></div>`;
    if (arr.length > 0) {
        html += `<div style='margin-top:8px;font-size:0.98em;color:#333;'>最近记录：<ul style='margin:0 0 0 18px;padding:0;max-height:90px;overflow-y:auto;'>`;
        let showArr = arr.slice(-5).reverse();
        for (let r of showArr) {
            let d = new Date(r.ts);
            html += `<li>${d.toLocaleDateString()} ${d.toLocaleTimeString().slice(0,5)} - <b>${formatTime(r.sec)}</b></li>`;
        }
        html += `</ul></div>`;
    }
    content.innerHTML = html;
} 
