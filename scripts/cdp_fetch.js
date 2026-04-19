const http = require('http');
const CDP = require('/opt/homebrew/lib/node_modules/chrome-remote-interface');

async function main() {
    const args = process.argv.slice(2);
    const mode = args[0];

    // 找ZSXQ tab
    const targets = await new Promise((resolve, reject) => {
        http.get('http://localhost:9222/json', (res) => {
            let data = '';
            res.on('data', c => data += c);
            res.on('end', () => resolve(JSON.parse(data)));
        }).on('error', reject);
    });
    const sourceTab = targets.find(t => t.url && t.url.includes('zsxq') && t.type === 'page');
    if (!sourceTab) { console.log('ERROR:no_zsxq_tab'); process.exit(1); }

    const sourceClient = await CDP({ target: sourceTab.webSocketDebuggerUrl });
    const { Page } = sourceClient;
    await Page.enable();

    if (mode === 'topics') {
        const groupId = args[1];
        const params = args[2] || 'scope=digests&count=3';
        // 新建tab导航
        const newTab = await sourceClient.Target.createTarget({ url: 'about:blank' });
        const newClient = await CDP({ target: newTab.targetId });
        const { Page: P2, Runtime: R2, Network: N2 } = newClient;
        await Promise.all([P2.enable(), R2.enable(), N2.enable()]);
        
        // 等待 networkidle
        new Promise(r => N2.loadingFinished(r));
        await P2.navigate({ url: `https://wx.zsxq.com/group/${groupId}?${params}` });
        await P2.waitForNavigation({ waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
        await new Promise(r => setTimeout(r, 1000));
        
        // 从新tab获取DOM文本
        const r = await R2.evaluate({
            expression: `document.body ? document.body.innerText : document.documentElement.innerText`,
            returnByValue: true
        });
        const text = r.result?.value || '';
        await newClient.close();
        
        try {
            // ZSXQ API在network请求中，不在DOM里。改用 Network.listInterceptors
            console.log('DOM text (first 100):', text.slice(0, 100));
        } catch(e) {}
        console.log('CDP_RESULT:' + JSON.stringify({ topics: [] }));

    } else if (mode === 'share_url') {
        const topicId = args[1];
        // 新建tab导航到ZSXQ组
        const newTab = await sourceClient.Target.createTarget({ url: 'about:blank' });
        const newClient = await CDP({ target: newTab.targetId });
        const { Page: P2, Runtime: R2, Network: N2 } = newClient;
        await Promise.all([P2.enable(), R2.enable(), N2.enable()]);
        
        // 先建cookie上下文
        await P2.navigate({ url: `https://wx.zsxq.com/group/15552545485212` });
        await P2.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
        await new Promise(r => setTimeout(r, 2000));
        
        // 手动调用XHR
        const r = await R2.evaluate({
            expression: `
                (function() {
                    var xhr = new XMLHttpRequest();
                    xhr.open('GET', 'https://api.zsxq.com/v2/topics/${topicId}/share_url', false);
                    xhr.withCredentials = true;
                    xhr.send(null);
                    if (xhr.status === 200 && xhr.responseText) {
                        try { return JSON.parse(xhr.responseText); } catch(e) { return null; }
                    }
                    return null;
                })()
            `,
            returnByValue: true
        });
        const resp = r.result?.value || {};
        const url = resp?.resp_data?.share_url || resp?.error || '';
        console.log('share_url:', url.slice(0, 50));
        await newClient.close();
        console.log('CDP_RESULT:' + JSON.stringify({ share_url: url }));
    }

    await sourceClient.close();
    process.exit(0);
}

main().catch(e => { console.log('ERROR:' + e.message.slice(0,200)); process.exit(1); });
