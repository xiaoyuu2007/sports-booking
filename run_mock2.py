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
        if (!_dom[id]) throw new Error("DOM element not found: " + id);
        return _dom[id]; 
    },
    querySelectorAll: function(sel) { return []; }
};

var window = { location: location };
var STANDARD_TIMES = ['08:00','09:00'];
var venues = [{id: '1', nodename: '羽毛球'}];
var VI = {'羽毛球':'🏸'};

function buildTimeChipsHtml(prefix) {
    let h = '<div class="drow">';
    for(let t of STANDARD_TIMES) {
        h += '<div class="dc ag-chip-'+prefix+'" data-time="'+t+'" onclick="this.classList.toggle(\'on\')">'+t+'</div>';
    }
    h += '</div>';
    return h;
}

// simulate loadVenues body
let opts = venues.map(v=>`<option value="${v.id}">${v.nodename}</option>`).join('');
document.getElementById('ag-primary-vid').innerHTML = opts;
document.getElementById('ag-primary-slots').innerHTML = buildTimeChipsHtml('primary');

let tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate()+1);
let ds = tomorrow.getFullYear()+'-'+String(tomorrow.getMonth()+1).padStart(2,'0')+'-'+String(tomorrow.getDate()).padStart(2,'0');
document.getElementById('ag-date').value = ds;

// simulate buildDates body
const now=new Date(), dn=['日','一','二','三','四','五','六'];
let h='';
for(let i=0;i<7;i++){
const d=new Date(now); d.setDate(now.getDate()+i);
const m=String(d.getMonth()+1).padStart(2,'0'),dd=String(d.getDate()).padStart(2,'0');
const ds=`${d.getFullYear()}-${m}-${dd}`;
const lb=i===0?'今天':i===1?'明天':`周${dn[d.getDay()]}`;
h+=`<div class="dc" id="d${ds}" onclick="pickD('${ds}',this)">${m}/${dd}<div class="dl">${lb}</div></div>`;
}
document.getElementById('drow').innerHTML=h;
const t = new Date(now); t.setDate(now.getDate()+1);
let selD = `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`;
const dEl = document.getElementById('d'+selD);
if(dEl) dEl.classList.add('on');
document.getElementById('sv1').textContent=selD + '，0人同行';
"""

ctx = MiniRacer()
try:
    ctx.eval(mock_js)
    print("No errors in logic")
except Exception as e:
    print(e)
