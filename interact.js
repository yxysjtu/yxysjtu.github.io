String.prototype.format = function(){
    if(arguments.length==0){
        return this;
    }
    for(var s=this, i=0; i<arguments.length; i++){
        s = s.replace(new RegExp("\\{"+i+"\\}","g"), arguments[i]);
    }
    return s;
};

var svg, textbox;
var pressedBtn = -1, followFlag = false;
var last_press_t = 0;
var viewBox = {x:0, y:0, width:400, height:100};
var fontsize = 6, color = "#007bff", fill = true;
var selectedObjects = [], selectedObject = null;
var svg_rect_prev, svg_rect;
var item_list = [];

window.onload = function(){
    //去掉默认的contextmenu事件，否则会和右键事件同时出现。
    document.oncontextmenu = function(e){
        e.preventDefault();
    };

    //tree view of file manager
    var toggler = document.getElementsByClassName("caret");
    for (var i = 0; i < toggler.length; i++) {
        console.log(i);
        toggler[i].addEventListener("click", function() {
        this.parentElement.querySelector(".nested").classList.toggle("active");
        this.classList.toggle("caret-down");
        });
    }
}
// window.onresize = function(){
//     svg_rect = svg.getBoundingClientRect();
//     var window_height = window.getBoundingClientRect().height;
//     svg_rect.height = window_height - 37;
//     viewBox.width = viewBox.width / svg_rect_prev.width * svg_rect.width;
//     viewBox.height = viewBox.height/ svg_rect_prev.height * svg_rect.height;
//     var geometry = viewBox.x+" "+viewBox.y+" "+viewBox.width+" "+viewBox.height;
//     svg.setAttributeNS(null, "viewBox", geometry);
//     svg_rect_prev = svg_rect;
// }

function open_tab(evt, tabName) {
    var i, tabcontent, tablinks;

    // Get all elements with class="tabcontent" and hide them
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }

    // Get all elements with class="tablinks" and remove the class "active"
    tablinks = document.getElementsByClassName("tablinks");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }

    // Show the current tab, and add an "active" class to the link that opened the tab
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";
}

function makeDraggable(evt) {
    svg = evt.target;
    textbox = document.getElementsByClassName("textbox")[0];

    svg.addEventListener('mouseover', mouseover);
    svg.addEventListener('wheel', mousescroll);
    svg.addEventListener('mousedown', mousedown);
    svg.addEventListener('mousemove', mousemove);
    svg.addEventListener('mouseup', mouseup);
    svg.addEventListener('mouseleave', mouseup);
    svg.addEventListener('touchstart', mousedown);
    svg.addEventListener('touchmove', mousemove);
    svg.addEventListener('touchend', mouseup);
    svg.addEventListener('touchleave', mouseup);
    svg.addEventListener('touchcancel', mouseup);

    var selectedElement, offset;

    //add shape
    function create_item(shape){
        new_svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        new_svg.setAttributeNS(null, "viewBox", "-2 -2 36 20");
        new_g = create_shape(shape, "text", 16, 8, 32, 16);
        new_g.onclick = function(evt){
            var float_shape = new Node(shape);
            selectedObject = float_shape;
            for(var obj of selectedObjects){
                obj.leave();
            }
            selectedObjects = [float_shape];
            followFlag = true;
            offset = getMousePosition(evt);
            float_shape.setPos(offset.x, offset.y);
        };
        new_svg.appendChild(new_g);
        new_div = document.createElement("div");
        new_div.setAttributeNS(null, "class", "item");
        new_div.appendChild(new_svg);
        item_list.push(new_g);
        return new_div;
    }
    
    object_bar = document.getElementById("object");
    object_bar.appendChild(create_item("oval"));
    object_bar.appendChild(create_item("parallelogram"));
    object_bar.appendChild(create_item("rectangle"));
    object_bar.appendChild(create_item("diamond"));


    svg_rect_prev = svg.getBoundingClientRect();
    viewBox.height = viewBox.width / svg_rect_prev.width * svg_rect_prev.height;
    var geometry = viewBox.x+" "+viewBox.y+" "+viewBox.width+" "+viewBox.height;
    svg.setAttributeNS(null, "viewBox", geometry);

    function getMousePosition(evt) {
        var CTM = svg.getScreenCTM();
        if (evt.touches) { evt = evt.touches[0]; }
        return {
            x: (evt.clientX - CTM.e) / CTM.a,
            y: (evt.clientY - CTM.f) / CTM.d
        };
    }

    function mousescroll(evt){//deltaY, up-125, down+125
        evt.preventDefault();

        var mouse_pos = getMousePosition(evt);
        var px = (mouse_pos.x - viewBox.x) / viewBox.width;
        var py = (mouse_pos.y - viewBox.y) / viewBox.height;
        var dw = evt.deltaY / 125;
        if(dw < 0){ // zoom in
            for(var i = 0; i < -dw && viewBox.width > 40; i++){
                viewBox.width /= 1.5;
            }
        }else{ // zoom out
            for(var i = 0; i < dw; i++){
                viewBox.width *= 1.5;
            }
        }
        viewBox.height = viewBox.width / svg_rect_prev.width * svg_rect_prev.height;

        //鼠标指的那点不动
        viewBox.x = mouse_pos.x - px * viewBox.width;
        viewBox.y = mouse_pos.y - py * viewBox.height;
        var geometry = viewBox.x+" "+viewBox.y+" "+viewBox.width+" "+viewBox.height;
        svg.setAttributeNS(null, "viewBox", geometry);
    }

    function mouseover(evt){ 
        if (evt.target.classList.contains('object')) {
            selectedElement = evt.target.parentNode;
            selectedObject = node_list.find((element) => element.g == selectedElement);
            if(selectedObject != null){
                selectedObject.hover();
            }
        }else{
            if(selectedObject != null && pressedBtn != 0 && !selectedObjects.includes(selectedObject)){
                selectedObject.leave();
            }
            selectedObject = null;
        }
    }
    
    
    function mousedown(evt) {
        evt.preventDefault();
        pressedBtn = evt.button;
        offset = getMousePosition(evt);

        if(pressedBtn == 0){
            //console.log(Date.now());
            if(selectedObject != null){//一种是鼠标按下对象，拖拽，弹起       
                if(!selectedObjects.includes(selectedObject)){
                    for(var obj of selectedObjects){
                        obj.leave();
                    }
                    selectedObjects = [selectedObject];
                }else if(selectedObjects.length == 1){
                    if(Date.now() - last_press_t < 500){ //double click
                        //console.log(textbox);
                        textbox.style.left = evt.clientX + "px";
                        textbox.style.top = evt.clientY + "px";
                        textbox.style.display = "block";
                        textbox.value = selectedObject.text.innerHTML;

                    }       
                }
                followFlag = true;
                last_press_t = Date.now();
                //console.log(selectedObjects);
            }else{//一种是鼠标按下画布，拖拽选框，弹起，再按下，得是对象，整体拖拽，弹起
                //hide textbox, update attributes
                if(textbox.style.display == "block"){
                    textbox.style.display = "none";
                    selectedObjects[0].text.innerHTML = textbox.value;
                    //TODO 更新其他参数，比如图形大小，字号，颜色，填充（注意更新的时候edge自动跟随）
                    
                }
                for(var obj of selectedObjects){
                    obj.leave();
                }
                selectedObjects = [];
                followFlag = false;
            }
        }

    }

    function mousemove(evt) {
        evt.preventDefault();

        var coord = getMousePosition(evt);
        
        if(pressedBtn == 2){ //right pressed => move canvas
            var dx = coord.x - offset.x;
            var dy = coord.y - offset.y;
            viewBox.x -= dx;
            viewBox.y -= dy;
            var geometry = viewBox.x+" "+viewBox.y+" "+viewBox.width+" "+viewBox.height;
            svg.setAttributeNS(null, "viewBox", geometry);
        }
        else if (followFlag) {
            var dx = coord.x - offset.x;
            var dy = coord.y - offset.y;
            if(selectedObjects.length == 1){
                selectedObjects[0].setPos(coord.x, coord.y);
            }else{
                for(var obj of selectedObjects){
                    obj.move(dx, dy);
                    offset = coord;
                }
            }
        }
    }

    function mouseup(evt) { //dehighlight
        pressedBtn = -1;
        followFlag = false;
    }
}