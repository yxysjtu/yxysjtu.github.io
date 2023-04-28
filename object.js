var node_list = [];
var edge_list = [];

function create_shape(shape, text, x, y, width, height){
    var new_shape;
    if(shape == "oval"){
        new_shape = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        var path = "M {0} {1} C {2} {3}, {4} {5}, {6} {7} L {8} {9} C {10} {11}, {12} {13}, {14} {15} L {16} {17}".format(x-width/2+height/2,y-height/2,
                                                                                                                            x-width/2,y-height/2,
                                                                                                                            x-width/2,y+height/2,
                                                                                                                            x-width/2+height/2,y+height/2,
                                                                                                                            x+width/2-height/2,y+height/2,
                                                                                                                            x+width/2,y+height/2,
                                                                                                                            x+width/2,y-height/2,
                                                                                                                            x+width/2-height/2,y-height/2,
                                                                                                                            x-width/2+height/2,y-height/2);
        new_shape.setAttributeNS(null, "d", path);
    }
    new_shape.setAttributeNS(null, "class", "object");
    var new_text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    new_text.setAttributeNS(null, "x", x);
    new_text.setAttributeNS(null, "y", y);
    new_text.setAttributeNS(null, "text-anchor", "middle");
    new_text.setAttributeNS(null, "font-size", fontsize+"px");
    new_text.setAttributeNS(null, "alignment-baseline", "middle");
    new_text.setAttributeNS(null, "class", "object");
    new_text.innerHTML = text;
    if(fill){
        new_shape.setAttributeNS(null, "fill", color);
        new_text.setAttributeNS(null, "fill", "#ffffff");
    }else{
        new_shape.setAttributeNS(null, "stroke", color);
        new_shape.setAttributeNS(null, "stroke-width", 1);
        new_shape.setAttributeNS(null, "fill", "#ffffff");
        new_text.setAttributeNS(null, "fill", "#000000");
    }
    var new_g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    new_g.setAttributeNS(null, "transform", "translate(0 0)");
    new_g.appendChild(new_shape);
    new_g.appendChild(new_text);
    return new_g;
}
//(x,y,shape,fill,text,fontsize,color)
//auto-scaling
class Node{ 
    constructor(shape){
        node_list.push(this);
        this.fill = fill;
        this.fontsize = fontsize;
        this.color = color;
        this.x = 0;
        this.y = 0;
        this.width = 32;
        this.height = 16;
        this.edges = [];
        this.g = create_shape(shape, "", this.x, this.y, this.width, this.height);
        this.shape = this.g.childNodes[0];
        this.text = this.g.childNodes[1];
        svg.appendChild(this.g);
    }

    hover() {
        if(this.fill){
            this.shape.setAttributeNS(null, "opacity", 0.8);
        }else{
            this.shape.setAttributeNS(null, "stroke", "#ff0000");
            this.text.setAttributeNS(null, "fill", "#ff0000");
        }
    }

    leave(){
        if(this.fill){
            this.shape.setAttributeNS(null, "opacity", 1);
        }else{
            this.shape.setAttributeNS(null, "stroke", color);
            this.text.setAttributeNS(null, "fill", "#000000");
        }
    }

    move(x, y){
        var transforms = this.g.transform.baseVal;

        // Get initial translation
        var transform = transforms.getItem(0);
        //dx += transform.matrix.e;
        //dy += transform.matrix.f;
        this.x = x;
        this.y = y;
        transform.setTranslate(x, y);
    }

    delete(){
        var index = node_list.findIndex((element) => element == this);
        node_list_l = node_list.slice(0, index);
        node_list_r = node_list.slice(index + 1);
        node_list = node_list_l.concat(node_list_r);
    }
}