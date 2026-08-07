from py_mini_racer import MiniRacer

mock_js = """
var location = { origin: 'http://localhost:8765' };

var _dom = {
    'vlist': { innerHTML: '' },
    'drow': { innerHTML: '' },
    'sv1': { textContent: '' },
    'uname': { textContent: '' },
    'ag-primary-vid': { innerHTML: '', value: '1', options: [{text: 'a'}], selectedIndex: 0 },
    'ag-primary-slots': { innerHTML: '' },
    'ag-date': { value: '' }
};

var document = {
    getElementById: function(id) { 
        if (!_dom[id]) _dom[id] = { innerHTML: '', textContent: '', value: '', classList: {add:function(){}, remove:function(){}} };
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
"""

ctx = MiniRacer()
ctx.eval(mock_js)

# We can modify the JS to assign the promise to a global variable
js_code = open('temp.js').read()
js_code = js_code.replace('(async()=>{', 'var globalPromise = (async()=>{')
ctx.eval(js_code)

try:
    # PyMiniRacer supports awaiting promises if we return them? No, it doesn't natively expose event loop
    # Let's just catch it in JS
    ctx.eval('globalPromise.catch(e => { throw e; })')
    # Wait, MiniRacer might not support event loops for promises out of the box...
    print("Done")
except Exception as e:
    print("Execution Error:", type(e))
    print(e)
