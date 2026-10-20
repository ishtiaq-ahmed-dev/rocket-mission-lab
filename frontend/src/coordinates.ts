import {Quaternion,Vector3} from 'three';
const basis=new Quaternion().setFromAxisAngle(new Vector3(1,0,0),-Math.PI/2),inverse=basis.clone().invert();
export const physicsPosition=(p:number[]):[number,number,number]=>[p[0],p[2],-p[1]];
export function physicsRotation(q:number[],out=new Quaternion()){
 return out.copy(basis).multiply(new Quaternion(q[1],q[2],q[3],q[0])).multiply(inverse);
}
