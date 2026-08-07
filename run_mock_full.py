from py_mini_racer import MiniRacer

mock_js = """
var location = { origin: 'http://localhost:8765' };

var _dom = {
    'vlist': { innerHTML: '<div class="ldg"><div class="spin"></div>加载中…</div>' },
    'drow': { innerHTML: '' },
    'sv1': { textContent: '' },
    'uname': { textContent: '' },
    'ag-primary-vid': { innerHTML: '', value: '1', options: [{text: 'a'}], selectedIndex: 0 },
    'ag-primary-slots': { innerHTML: '' },
    'ag-date': { value: '' }
};

var document = {
    getElementById: function(id) { 
        if (!_dom[id]) {
            console.log("DOM element not found: " + id);
            return { innerHTML: '', textContent: '', value: '', classList: {add:function(){}, remove:function(){}} };
        }
        return _dom[id]; 
    },
    querySelectorAll: function(sel) { return []; }
};

var window = { location: location };
var fetch = function(url, opts) {
    if (url.includes('/api/user')) return Promise.resolve({json: function(){ return Promise.resolve({success: true, data: {username: 'test', idserial: '123'}}); }});
    if (url.includes('/api/venues')) return Promise.resolve({json: function(){ return Promise.resolve({success: true, data: [{id: '1', nodename: '羽毛球'}]}); }});
    return Promise.resolve({json: function(){ return Promise.resolve({}); }});
};
var setTimeout = function(cb, t) {};
var clearTimeout = function(id) {};

var console = {
    log: function(msg) { },
    error: function(msg) { }
};

var result_errors = [];
"""

js = open('script_from_server_v2.js').read().replace('<script>','').replace('</script>','').replace('</body>','').replace('</html>','')
# Make IIFE global promise
js = js.replace('(async()=>{', 'var globalPromise = (async()=>{')

ctx = MiniRacer()
ctx.eval(mock_js)
ctx.eval(js)

ctx.eval("""
globalPromise.then(() => {
    // Check if vlist still has 加载中
    var vlist = document.getElementById('vlist').innerHTML;
    if (vlist.includes('加载中')) {
        result_errors.push("STUCK_LOADING");
    }
}).catch(e => {
    result_errors.push("PROMISE_ERROR: " + e.toString());
});
""")

# We need to wait for JS promises to settle... 
# Py_mini_racer does NOT run an event loop by default. But it handles native promises?
# Let's test if it works.
print("Result:", ctx.eval("result_errors.join(\",\")"))
