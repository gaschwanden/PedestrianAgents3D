
import processing.core.PApplet;
import processing.core.PFont;

public class Button {
	PApplet p;
	int x;
	int y;
	int w; 
	int h;
	String id;
	String dname="";
	public boolean over = false;
	public boolean down = false;
	PFont font;
	
	public Button(PApplet _p, String _n,  int _x, int _y, int _w, int _h) {
		p=_p;
		x=_x;
		y=_y;
		w=_w;
		h=_h;
		id =_n;
		
		if      (id.equals("display pathoverlap")) 			dname = "P";
		else if (id.equals("display facadevisibility")) 	dname = "F";
		else if (id.equals("display facadevisibilityO")) 	dname = "Fx";
		else if (id.equals("display traces")) 				dname = "TR";
		else if (id.equals("display tracesO")) 				dname = "TRx";
		else if (id.equals("add OD")) 						dname = "OD+";
		else if (id.equals("delete OD")) 					dname = "OD-";
		else if (id.equals("OD weight")) 					dname = "+/-";
		else if (id.equals("save ODs")) 					dname = "save";
		else if (id.equals("load ODs")) 					dname = "open";
		else if (id.equals("add building"))					dname = "B+";
		else if (id.equals("edit building"))				dname = "B";
		else if (id.equals("move building"))				dname = "Bm";
		else if (id.equals("delete building"))				dname = "B-";
		else if (id.equals("load buildings"))				dname = "load";
		else if (id.equals("save buildings"))				dname = "save";
		else if (id.equals("add obstacle"))					dname = "O+";
		else if (id.equals("edit obstacle"))				dname = "O";
		else if (id.equals("move obstacle"))				dname = "OBm";
		else if (id.equals("delete obstacle"))				dname = "O-";
		else if (id.equals("load obstacles"))				dname = "load";
		else if (id.equals("save obstacles"))				dname = "save";
		else if (id.equals("add module"))				    dname = "M";
		else if (id.equals("move module"))				    dname = "Mm";
		else if (id.equals("rotate module"))				dname = "Mr";
		else if (id.equals("delete module"))				dname = "M-";
		else if (id.equals("isovist"))						dname = "Iso";
		else if (id.equals("reset everything"))				dname = "X";

		
		//font = p.loadFont("TheSansSemiBold-Plain-12.vlw");
	}
	
	public void draw(Scene scene) {
		p.noStroke();
		p.rectMode(PApplet.CORNER);
		//p.textFont(font);
		down = false;
		if (id.equals("add OD") 					&& scene.interaction_mode == Scene.mode_OD) 		down=true; 
		if (id.equals("delete OD") 					&& scene.interaction_mode == Scene.mode_OD_delete) 	down=true; 
		if (id.equals("OD weight") 					&& scene.interaction_mode == Scene.mode_OD_weight)  down=true;
		if (id.equals("add building") 				&& scene.interaction_mode == Scene.mode_BD_add) 	down=true; 
		if (id.equals("edit building") 				&& scene.interaction_mode == Scene.mode_BD_edit) 	down=true; 
		if (id.equals("move building") 				&& scene.interaction_mode == Scene.mode_BD_move) 	down=true;
		if (id.equals("delete building")			&& scene.interaction_mode == Scene.mode_BD_delete) 	down=true; 
		if (id.equals("edit obstacle") 				&& scene.interaction_mode == Scene.mode_OB_edit) 	down=true; 
		if (id.equals("add obstacle") 				&& scene.interaction_mode == Scene.mode_OB_add) 	down=true;
		if (id.equals("move obstacle") 				&& scene.interaction_mode == Scene.mode_OB_move) 	down=true;
		if (id.equals("delete obstacle")			&& scene.interaction_mode == Scene.mode_OB_delete) 	down=true;
		if (id.equals("add module") 				&& scene.interaction_mode == Scene.mode_MD_add) 	down=true; 
		if (id.equals("move module") 				&& scene.interaction_mode == Scene.mode_MD_move) 	down=true;
		if (id.equals("rotate module") 				&& scene.interaction_mode == Scene.mode_MD_rotate) 	down=true;
		if (id.equals("delete module")				&& scene.interaction_mode == Scene.mode_MD_delete) 	down=true; 
		
		if (id.equals("isovist") 					&& scene.show_iso) 									down=true;
		
		if (id.equals("display pathoverlap") 		&& scene.analysis_mode == Scene.display_pathoverlap) 		down=true;
		if (id.equals("display facadevisibility")	&& scene.analysis_mode == Scene.display_facadevisibility) 	down=true; 
		if (id.equals("display facadevisibilityO")	&& scene.analysis_mode == Scene.display_facadevisibilityO) 	down=true;
		if (id.equals("display traces")				&& scene.analysis_mode == Scene.display_traces) 			down=true; 
		if (id.equals("display tracesO")			&& scene.analysis_mode == Scene.display_tracesO) 			down=true;
		
		p.pushMatrix();
			p.translate(x, y);
			p.fill(100,0,0);
			
			if (down) p.fill(200,0,0);
			if (over) p.fill(255,0,0);
			p.rect(0, 0, w, h);
			
			p.fill(0);
			p.textAlign(PApplet.CENTER);
			p.text(dname, w/2.0f,h/2.0f+4);
		p.popMatrix();
	}
	
	public String getName()
	{
		//p.println(name);
		return id;
	}
}
