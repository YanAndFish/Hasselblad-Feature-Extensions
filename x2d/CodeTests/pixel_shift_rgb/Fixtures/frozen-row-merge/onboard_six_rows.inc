/* 原六张离线 GRBG 重建的逐行实现；保留原厂数值域，尚需验证显影 CFA 相位。 */
struct six_half_row { uint16_t values[W][3]; unsigned char valid[W]; };
static struct six_half_row half_rows[2];
static uint16_t rounded_mean(unsigned sum,unsigned count) {
 unsigned quotient=sum/count,remainder=sum%count;
 if(remainder*2>count || (remainder*2==count && (quotient&1)))quotient++;
 return (uint16_t)quotient;
}
static void six_half(unsigned y,struct six_half_row *dst) {
 static const unsigned cfa[2][2]={{0,1},{3,2}};
 memset(dst,0,sizeof(*dst));
 for(unsigned i=4;i<6;i++) {
  unsigned sy=y+(i==4?1:0);
  if(fseek(inputs[i],16384L+(long)(sy+92)*23808L,SEEK_SET))fail("half-grid seek");
  if(fread(input_row,2,11904,inputs[i])!=11904)fail("half-grid row read");
  for(unsigned x=0;x<W;x++) {
   unsigned c=cfa[sy%2][(x+1)%2];if(c==3)c=1;
   if(dst->valid[x]&(1u<<c))fail("duplicate half-grid channel");
   dst->values[x][c]=input_row[125+x];dst->valid[x]|=(unsigned char)(1u<<c);
  }
 }
 for(unsigned x=0;x<W;x++)if(dst->valid[x]!=3 && dst->valid[x]!=6)fail("incomplete half-grid");
}
static void six_output_rows(unsigned y,uint16_t a[W][4],uint16_t b[W][4]) {
 struct six_half_row *cur=&half_rows[y%2],*prev=&half_rows[(y+1)%2];
 six_half(y,cur);if(y==0)prev=cur;
 for(unsigned x=0;x<W;x++) {
  unsigned next=x+1<W?x+1:x,previous=x?x-1:0;
  output_rows[2*x]=(uint16_t)(((unsigned)a[x][1]+a[x][3]+1)/2);
  output_rows[2*W+2*x+1]=cur->values[x][1];
  unsigned sum=(unsigned)a[x][0]+a[next][0],count=2;
  if(prev->valid[x]&1){sum+=prev->values[x][0];count++;}
  if(cur->valid[x]&1){sum+=cur->values[x][0];count++;}
  output_rows[2*x+1]=rounded_mean(sum,count);
  sum=(unsigned)a[x][2]+b[x][2];count=2;
  if(cur->valid[x]&4){sum+=cur->values[x][2];count++;}
  if(cur->valid[previous]&4){sum+=cur->values[previous][2];count++;}
  output_rows[2*W+2*x]=rounded_mean(sum,count);
 }
}
