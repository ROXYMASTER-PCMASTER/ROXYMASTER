// tabla_editable.js - convierte una tabla html en editable con doble clic
// fuente: implementacion propia

class TablaEditable {
  constructor(selector, apiUrl) {
    this.tabla = document.querySelector(selector);
    this.apiUrl = apiUrl;
    this.init();
  }

  init() {
    this.tabla.addEventListener("dblclick", (e) => {
      var td = e.target.closest("td");
      if (td && td.dataset.columna) this.editar(td);
    });
  }

  editar(td) {
    var orig = td.textContent;
    var inp = document.createElement("input");
    inp.value = orig;
    inp.className = "editable-input";
    td.textContent = "";
    td.appendChild(inp);
    inp.focus();
    inp.onblur = () => this.guardar(td, inp.value, orig);
  }

  async guardar(td, nuevo, orig) {
    if (nuevo === orig) { td.textContent = orig; return; }
    var id = td.closest("tr").dataset.id;
    var col = td.dataset.columna;
    var r = await fetch(this.apiUrl + "/" + id, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [col]: nuevo })
    });
    td.textContent = r.ok ? nuevo : orig;
  }
}

var stEdit = document.createElement("style");
stEdit.textContent = ".editable-input{background:#0d1117;border:1px solid #58a6ff;color:#c9d1d9;padding:2px 6px;border-radius:4px;width:100%}";
document.head.appendChild(stEdit);
