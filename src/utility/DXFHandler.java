package utility;

import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;

public class DXFHandler {

	PApplet p;

	DXFLine activeLine 		= null;
	DXFPoly activePoly 		= null;
	DXFMesh activeMesh 		= null;
	DXFLWPoly activeLWPoly 	= null;

	boolean doVertices = false;
	boolean doFaces = false;
	int facecount = 0;
	int numVertices;
	int numFaces;
	int vertexCount;
	int currVertexCount;

	public Vector<DXFLine> 		lines;
	public Vector<DXFPoly> 		polys;
	public Vector<DXFLWPoly> 	lwpolys;
	public Vector<DXFMesh> 		meshes;

	private int countPolyFaceMesh = 0;

	private DXFMesh activePolyFaceMesh;

	private boolean doPolyFaceMesh;

	private int currentvortices = 0;

	public DXFHandler(PApplet _p) {
		p=_p;
	}

	public void importDXF(String path, boolean verbose)
	{
		boolean doEntities = false;
		lines = new Vector<DXFLine>(); 
		polys = new Vector<DXFPoly>(); 
		meshes = new Vector<DXFMesh>();
		lwpolys = new Vector<DXFLWPoly>();
		activeLine = null;

		BufferedReader br=null;

		try {
			br=new BufferedReader(new FileReader(path));
		} catch (FileNotFoundException e1) {
			e1.printStackTrace();
			p.exit();
			return;
		}

		String sval,skey;
		boolean eof = false;

		try {
			while(!eof){
				skey=br.readLine(); if (skey==null) { eof=true; continue; }
				skey=skey.trim();
				sval=br.readLine(); if (sval==null) { eof=true; continue; }
				sval=sval.trim();


				if (skey.equals("0")) {
					//p.println(skey+" "+sval);
					if (sval.equals("SECTION")) {
						skey=br.readLine(); if (skey==null) { eof=true; continue; }
						skey=skey.trim();
						sval=br.readLine(); if (sval==null) { eof=true; continue; }
						sval=sval.trim();
						if (skey.equals("2")) {
							if (sval.equals("ENTITIES")) {
								doEntities = true;
								//p.println("do entities");
								continue;
							}
							else {
								doEntities = false;
								continue;
							}
						}
					}
					else if (sval.equals("ENDSEC")) {
						doEntities = false;
						continue;
					}
				}
				//
				if (doEntities) {
					//if (verbose) p.println(skey+" "+sval);
					//if (skey.equals("0")) p.println(skey+" "+sval);
					if (skey.equals("0") && sval.equals("LINE")) { 
						// finish whatever we are doing
						finishObjectImport();
						activeLine = new DXFLine();
						continue;
					}

					else if (skey.equals("0") && sval.equals("POLYLINE")) { 
						countPolyFaceMesh++;
						System.out.println(path +" found an Polyline "+countPolyFaceMesh );

						// finish whatever we are doing

						finishObjectImport();
						activePoly = new DXFPoly();
						doVertices = false;
						numVertices = 0;
						numFaces = 0;
						vertexCount = 0;
						//p.println("");
						//p.println("polyline");
						continue;
					}
					else if (skey.equals("0") && sval.equals("LWPOLYLINE")) { 
						countPolyFaceMesh++;
						System.out.println(path +" found an LWPolyline "+countPolyFaceMesh );


						// finish whatever we are doing
						finishObjectImport();
						activeLWPoly = new DXFLWPoly();
						//p.println("");
						//if (verbose) p.println("lwpolyline");
						continue;
					}
					else if (skey.equals("0") && sval.equals("MESH")) { 
						System.out.println(path +" found an Mesh "+countPolyFaceMesh );

						finishObjectImport();  
						activeMesh = new DXFMesh();
						doFaces = false;
						facecount = -1;
						continue;
					}
					else if (skey.equals("100") && sval.equals("AcDbPolyFaceMesh")) { 

						countPolyFaceMesh++;
						currentvortices = 0;
						System.out.println("found an AcDbPolyFaceMesh "+countPolyFaceMesh );
						finishObjectImport();  
						activePolyFaceMesh = new DXFMesh();
						doPolyFaceMesh = false;
						facecount = -1;
						continue;
					}
					// types we are not doing (yet)
					else if (skey.equals("0") && sval.equals("3DFACE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("3DSOLID")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("ACAD_PROXY_ENTITY")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("ARC")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("ATTDEF")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("ATTRIB")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("3DFACE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("3DSOLID")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("BODY")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("CIRCLE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("DIMENSION")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("ELLIPSE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("HATCH")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("IMAGE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("INSERT")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("LEADER")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("LWPOLYLINE")) { 
						finishObjectImport();  continue;
					}

					else if (skey.equals("0") && sval.equals("MLINE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("MTEXT")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("OLEFRAME")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("OLE2FRAME")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("POINT")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("RAY")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("REGION")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("SHAPE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("SOLID")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("SPLINE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("TEXT")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("TOLERANCE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("TRACE")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("VIEWPORT")) { 
						finishObjectImport();  continue;
					}
					else if (skey.equals("0") && sval.equals("XLINE")) { 
						finishObjectImport();  continue;
					}
					// now import the actual geometry
					if (activeLine!=null)
						importLine(skey, sval);
					if (activePoly!=null)
						importPoly(skey, sval);
					if (activeMesh!=null)
						importMesh(skey, sval);
					if (activeLWPoly!=null)
						importLWPoly(skey, sval);
					if (activePolyFaceMesh!=null) importPolyFaceMesh(skey, sval);
				}

			}
		}
		catch (IOException e) {
			e.printStackTrace();
		}	
		// finish unfinished...
		finishObjectImport();
	}
	private void importPolyFaceMesh(String skey, String sval) {
		//p.println(skey+" "+sval);
		//		if (skey.equals("8")) {
		//			activeMesh.layer = sval; return;
		//		}

		if (skey.equals("10")) {
			activePolyFaceMesh.vertices.addElement(new DXFVertex());
			activePolyFaceMesh.vertices.lastElement().x = (float) Double.parseDouble(sval); return;
		}
		if (skey.equals("20")) {
			activePolyFaceMesh.vertices.lastElement().y = (float) Double.parseDouble(sval)*-1; return;
		}
		if (skey.equals("30")) {
			activePolyFaceMesh.vertices.lastElement().z = (float) Double.parseDouble(sval); return;

		}


		//		
		//		if (skey.equals("93") && facecount == -1) {  // is not actually the facecount but the number of markers and vertices in this section...
		//			doFaces = true;
		//			facecount = Integer.parseInt(sval);
		//			vertexCount = -1;  // init
		//			currVertexCount = 0;
		//			
		//			//p.println(facecount);
		//			return;
		//		}
	}

	private void importMesh(String skey, String sval) {
		//p.println(skey+" "+sval);
		if (skey.equals("8")) {
			activeMesh.layer = sval; return;
		}

		if (skey.equals("10")) {
			activeMesh.vertices.addElement(new DXFVertex());
			activeMesh.vertices.lastElement().x = (float) Double.parseDouble(sval); return;
		}
		if (skey.equals("20")) {
			activeMesh.vertices.lastElement().y = (float) Double.parseDouble(sval)*-1; return;
		}
		if (skey.equals("30")) {
			activeMesh.vertices.lastElement().z = (float) Double.parseDouble(sval); return;
		}

		if (skey.equals("93") && facecount == -1) {  // is not actually the facecount but the number of markers and vertices in this section...
			doFaces = true;
			facecount = Integer.parseInt(sval);
			vertexCount = -1;  // init
			currVertexCount = 0;

			//p.println(facecount);
			return;
		}



		if (skey.equals("94")) {
			doFaces = false;
			return;
		}
		if (doFaces) {  // now comes a long list of 
			// first 90 - number vertices of the next face
			// then 90 - vertex ref, 90-vertex ref, usw
			// then, again 90 - number of vertices
			// usw


			if (vertexCount==-1 || (vertexCount <= currVertexCount)) {
				if (skey.equals("90")) { // read number vertices to come

					vertexCount = Integer.parseInt(sval);
					currVertexCount = 0;
					activeMesh.faces.addElement(new DXFFace());
					//p.println("now getting num of vertices: "+vertexCount);
					return;
				}
			}
			else {  // read a vertex
				if (skey.equals("90")) {
					int index = Integer.parseInt(sval);
					activeMesh.faces.lastElement().vertices.addElement(activeMesh.vertices.elementAt(index));
					currVertexCount++;
					//p.println("...adding vertex: "+index);
					return;
				}
			}
		}
	}

	private void importLWPoly(String skey, String sval) {
		//p.println(skey+" "+sval);
		if (skey.equals("8")) {
			activeLWPoly.layer = sval; return;
		}
		if (skey.equals("10")) {
			activeLWPoly.addVertex();
			activeLWPoly.vertices.elementAt(activeLWPoly.vertices.size()-1).x = Double.parseDouble(sval); return;
		}
		if (skey.equals("20")) {
			activeLWPoly.vertices.elementAt(activeLWPoly.vertices.size()-1).y =Double.parseDouble(sval)*-1; return;
		}
		if (skey.equals("30")) {
			activeLWPoly.vertices.elementAt(activeLWPoly.vertices.size()-1).z = Double.parseDouble(sval); return;
		}
	}

	private void importPoly(String skey, String sval) {
		//p.println(skey+" "+sval);
		if (skey.equals("0") && sval.equals("SEQEND")) {  // end the polyline
			//p.println("finish: "+numVertices+" - "+(activePoly.vertices.size())+", "+numFaces+" - "+(activePoly.faces.size()));
			finishObjectImport(); 

			return;
		}
		if (skey.equals("0") && sval.equals("VERTEX")) { // starting doing the vertices
			doVertices = true;
			vertexCount++;
			if (activePoly.vertices.size() < (numVertices)  || numVertices==0) {
				activePoly.addVertex();
				//p.println("...add vertex");
			}
			else  {
				activePoly.addFace();
				//p.println("...add face");
			}
			return;
		}

		// read layer, number of vertices, number of faces, before we start with the vertices
		if (!doVertices) {  
			if (skey.equals("8")) {
				System.out.println("layer = "+sval);
				activePoly.layer = sval; return;
			}
			if (skey.equals("71")) {
				numVertices = Integer.parseInt(sval); 
				System.out.println("vertices = "+ Integer.parseInt(sval));
				return;
			}
			if (skey.equals("72")) {
				System.out.println("faces = "+ Integer.parseInt(sval));
				numFaces = Integer.parseInt(sval); return;
			}
		}

		//read vertex info
		if (doVertices) { 

			if (vertexCount <= (numVertices) || numVertices==0) { // add info to vertex
				if (skey.equals("10")) {
					activePoly.vertices.elementAt(activePoly.vertices.size()-1).x = Double.parseDouble(sval); return;
				}
				if (skey.equals("20")) {
					activePoly.vertices.elementAt(activePoly.vertices.size()-1).y =Double.parseDouble(sval)*-1; return;
				}
				if (skey.equals("30")) {
					activePoly.vertices.elementAt(activePoly.vertices.size()-1).z = Double.parseDouble(sval); return;
				}
			}
			else {  // add info to face
				if (skey.equals("71") || skey.equals("72") || skey.equals("73") || skey.equals("74")) {
					int vIndex = Integer.parseInt(sval);
					int vertexIndex = p.abs(vIndex) - 1;
					activePoly.faces.elementAt(activePoly.faces.size()-1).vertices.addElement(activePoly.vertices.elementAt(vertexIndex)); 
					activePoly.faces.elementAt(activePoly.faces.size()-1).visible.addElement(vIndex > 0);
					return;
				}
			}
		}
	}

	private void importLine(String skey, String sval) {
		//p.println(skey+" "+sval);
		if 		(skey.equals("8"))	activeLine.layer = sval;
		else if (skey.equals("10"))	activeLine.x1 = Float.parseFloat(sval);
		else if (skey.equals("20"))	activeLine.y1 = Float.parseFloat(sval)*-1;
		else if (skey.equals("30"))	activeLine.z1 = Float.parseFloat(sval);
		else if (skey.equals("11"))	activeLine.x2 = Float.parseFloat(sval);
		else if (skey.equals("21"))	activeLine.y2 = Float.parseFloat(sval)*-1;
		else if (skey.equals("31"))	activeLine.z2 = Float.parseFloat(sval);
		//else p.println(skey+" "+sval);
	}

	private void finishObjectImport() {
		// if there is an active object
		if (activeLine != null) {
			lines.addElement(activeLine);
			activeLine = null;
		}

		if (activePoly != null) {
			// quick fix for different poly formats:
			if (activePoly.faces.size()==0) activePoly.addFaceFromVertexList();
			polys.addElement(activePoly);
			activePoly = null;
		}
		if (activeMesh != null) {
			//activeMesh.setProperties();
			meshes.addElement(activeMesh);
			//p.println(activeMesh.vertices.size());
			activeMesh = null;
		}
		if (activePolyFaceMesh != null) {
			setFaces(activePolyFaceMesh);
			//activeMesh.setProperties();
			meshes.addElement(activePolyFaceMesh);
			//p.println(activeMesh.vertices.size());
			activePolyFaceMesh = null;
		}

		if (activeLWPoly != null) {
			lwpolys.addElement(activeLWPoly);
			activeLWPoly = null;
		}

	}

	private void setFaces(DXFMesh activePolyFaceMesh2) {

		for(int i = 0; i< activePolyFaceMesh2.vertices.size();i++){
			System.out.println( "looping "+i);

			if (i>1){ 
				System.out.println(activePolyFaceMesh.vertices.elementAt(i).x+ " = "+activePolyFaceMesh.vertices.elementAt(i-1).x);

				if(activePolyFaceMesh.vertices.elementAt(i) == activePolyFaceMesh.vertices.elementAt(i-1)){
					activePolyFaceMesh.faces.addElement(new DXFFace());
					System.out.println("I'm in");

					for(int j = currentvortices; j<i;j++){
						System.out.println( "looping j ="+j);
						activePolyFaceMesh.faces.lastElement().vertices.addElement(activePolyFaceMesh.vertices.elementAt(j));
					}
					currentvortices = activePolyFaceMesh.vertices.size();
				}
			}
		}



	}

}
