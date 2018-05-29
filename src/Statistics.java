import processing.core.PApplet;
import processing.core.PFont;


public class Statistics {
	Button[] buttons = new Button[50];
	PApplet p;
	PFont font;
	Scene scene;
	
	public Statistics(PApplet _p, Scene _scene)
	{
		p=_p;
		scene=_scene;
		//font = p.loadFont("TheSansSemiBold-Plain-14.vlw");
		int incr  = 30;
		int startx = 10;
		int x = startx; int y = 10;
		int i = 0;
		buttons[i]   = new Button(p, "display pathoverlap",   		x, y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "display facadevisibility",   	x, y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "display facadevisibilityO",   x, y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "display traces",   			x, y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "display tracesO",   			x, y, 28, 28); i++; x+=incr;
		x=startx; y+= incr;
		
		buttons[i]   = new Button(p, "add OD", 						x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "delete OD", 					x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "OD weight", 					x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "load ODs", 					x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "save ODs", 					x,  y, 28, 28); i++; x+=incr;
		x=startx; y+= incr;
		
		buttons[i]   = new Button(p, "add building", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "edit building", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "move building", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "delete building", 			x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "load buildings", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "save buildings", 				x,  y, 28, 28); i++; x+=incr;
		x=startx; y+= incr;
		
		buttons[i]   = new Button(p, "add obstacle", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "edit obstacle", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "move obstacle", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "delete obstacle", 			x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "load obstacles", 				x,  y, 28, 28); i++; x+=incr;
		buttons[i]   = new Button(p, "save obstacles", 				x,  y, 28, 28); i++; x+=incr;
		x=startx; y+= incr;
		
		//buttons[i]   = new Button(p, "add module", 				x,  y, 28, 28); i++; x+=incr;
		//buttons[i]   = new Button(p, "move module", 				x,  y, 28, 28); i++; x+=incr;
		//buttons[i]   = new Button(p, "rotate module", 			x,  y, 28, 28); i++; x+=incr;
		//buttons[i]   = new Button(p, "delete module", 			x,  y, 28, 28); i++; x+=incr;
		//x=startx; y+= incr;
		
		buttons[i]   = new Button(p, "isovist", 				    x,  y, 28, 28); i++; x+=incr;
		x=startx; y+= incr;
		
		buttons[i]   = new Button(p, "reset everything", 			x, y, 28, 28); i++; x+=incr;
		x=startx; y+= incr;
	}
	
	public void draw() {
		//p.textFont(font);
		//System.out.println("fgh");
		for (int i = 0; i < buttons.length; i++) {
			if (buttons[i]==null) continue;
			buttons[i].draw(scene);
		}
		p.fill(100);
		p.textAlign(PApplet.LEFT);
		p.text(p.frameRate, 10,p.height-10);
		//p.text(scene.agents.size(), 10,p.height-20);
	}
	
	///////////////////////////////////////////////////////////
	// interaction

	public int over(int _x, int _y) {
		int ret = -1;
		int a,b;
		int tol = 20;
		for (int i = 0; i < buttons.length; i++) {
			if (buttons[i] == null) continue;
			a = buttons[i].x ;
			b = buttons[i].y ;
	
			if (_x>a && _x<(a+buttons[i].w) && _y>b && _y<(b+buttons[i].h)) {
				buttons[i].over = true;
				ret = 1;
			}
			if (_x>a-tol && _x<(a+buttons[i].w + tol) && _y>b-tol && _y<(b+buttons[i].h) + tol) {
				ret = 1;
			}
		}
	
		// generally - return true if we are anywhere over any button or slider or text
		//if (_x > (p.width - left) && _y < bottom) ret = 1;
		return ret;
	}
	
	public void releaseButtons() {
		for (int i = 0; i < buttons.length; i++) {
			if (buttons[i] == null) continue;
			buttons[i].over = false;
		}
	}
	
	public void buttonAction( ) {
		for (int i = 0; i < buttons.length; i++) {
			if (buttons[i] == null) continue;

			if (buttons[i].over) {
				// in any case: reset selection
				//network.deselectElements();
				//buttons[i].down = true;
				if      (buttons[i].id.equals("add OD")) 		 {
					if (scene.interaction_mode!= scene.mode_OD) 			scene.interaction_mode = scene.mode_OD;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("delete OD")) 	 {
					if (scene.interaction_mode != scene.mode_OD_delete)		scene.interaction_mode = scene.mode_OD_delete;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("OD weight"))					{
					if (scene.interaction_mode != scene.mode_OD_weight)		scene.interaction_mode = scene.mode_OD_weight;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("save ODs"))					scene.notifySaveODs = true;
				else if (buttons[i].id.equals("load ODs"))					scene.notifyLoadODs = true;
				
				else if (buttons[i].id.equals("add building"))  {
					if (scene.interaction_mode != scene.mode_BD_add) 		scene.interaction_mode = scene.mode_BD_add;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("edit building"))  {
					if (scene.interaction_mode != scene.mode_BD_edit) 		scene.interaction_mode = scene.mode_BD_edit;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("move building"))  {
					if (scene.interaction_mode != scene.mode_BD_move) 		scene.interaction_mode = scene.mode_BD_move;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("delete building")){
					if (scene.interaction_mode != scene.mode_BD_delete) 	scene.interaction_mode = scene.mode_BD_delete;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("save buildings"))			scene.notifySaveBuildings = true;
				else if (buttons[i].id.equals("load buildings"))			scene.notifyLoadBuildings = true;
				
				else if (buttons[i].id.equals("add obstacle"))  {
					if (scene.interaction_mode != scene.mode_OB_add) 		scene.interaction_mode = scene.mode_OB_add;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("edit obstacle"))  {
					if (scene.interaction_mode != scene.mode_OB_edit) 		scene.interaction_mode = scene.mode_OB_edit;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("move obstacle"))  {
					if (scene.interaction_mode != scene.mode_OB_move) 		scene.interaction_mode = scene.mode_OB_move;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("delete obstacle")){
					if (scene.interaction_mode != scene.mode_OB_delete) 	scene.interaction_mode = scene.mode_OB_delete;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("save obstacles"))			scene.notifySaveObstacles = true;
				else if (buttons[i].id.equals("load obstacles"))			scene.notifyLoadObstacles = true;
				
				else if (buttons[i].id.equals("add module"))  {
					if (scene.interaction_mode != scene.mode_MD_add) 		scene.interaction_mode = scene.mode_MD_add;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("move module"))  {
					if (scene.interaction_mode != scene.mode_MD_move) 		scene.interaction_mode = scene.mode_MD_move;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("rotate module"))  {
					if (scene.interaction_mode != scene.mode_MD_rotate) 	scene.interaction_mode = scene.mode_MD_rotate;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				else if (buttons[i].id.equals("delete module")){
					if (scene.interaction_mode != scene.mode_MD_delete) 	scene.interaction_mode = scene.mode_MD_delete;
					else													scene.interaction_mode = scene.mode_noInteraction;
				}
				
				else if (buttons[i].id.equals("display pathoverlap"))  		{
					if ( scene.analysis_mode != scene.display_pathoverlap) 		scene.analysis_mode = scene.display_pathoverlap;
					else										{ scene.analysis_mode = scene.display_noAnalysis; scene.notifyResetAnalysis(); }
				}
				else if (buttons[i].id.equals("display facadevisibility"))	{
					if (scene.analysis_mode != scene.display_facadevisibility) 	scene.analysis_mode = scene.display_facadevisibility;
					else										{ scene.analysis_mode = scene.display_noAnalysis; scene.notifyResetAnalysis(); }
				}
				else if (buttons[i].id.equals("display facadevisibilityO"))	{
					if (scene.analysis_mode != scene.display_facadevisibilityO) 	scene.analysis_mode = scene.display_facadevisibilityO;
					else										{ scene.analysis_mode = scene.display_noAnalysis; scene.notifyResetAnalysis(); }
				}
				else if (buttons[i].id.equals("display traces"))			{
					if (scene.analysis_mode != scene.display_traces) 				scene.analysis_mode = scene.display_traces;
					else										{ scene.analysis_mode = scene.display_noAnalysis; scene.notifyResetAnalysis(); }
				}
				else if (buttons[i].id.equals("display tracesO"))			{
					if (scene.analysis_mode != scene.display_tracesO) 				scene.analysis_mode = scene.display_tracesO;
					else										{ scene.analysis_mode = scene.display_noAnalysis; scene.notifyResetAnalysis(); }
				}
				
				else if (buttons[i].id.equals("isovist"))					scene.show_iso = !scene.show_iso; 
				else if (buttons[i].id.equals("reset everything"))			scene.notifyAppRenew = true; 
			}
		}
	}
}
