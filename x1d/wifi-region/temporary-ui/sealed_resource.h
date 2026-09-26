#ifndef HBL_SEALED_RESOURCE_H
#define HBL_SEALED_RESOURCE_H
#include <QtCore/QResource>
#include <QtCore/QFile>
#include <QtCore/QByteArray>
#include <QtCore/QStringList>
extern "C" __attribute__((visibility("hidden"))) int hbl_resource_open(unsigned char *,size_t,const unsigned char *,size_t);

static bool registerSealedResource(const QString &path,const QString &root) {
 // QResource 保存数据指针，资源内存必须一直保持到进程结束。
 static QByteArray *plain=nullptr;
 static QStringList roots;
 if(roots.contains(root))return true;
 if(!plain){
  QFile file(path);
  if(!file.open(QIODevice::ReadOnly)||file.size()<=48||file.size()>32*1024*1024+48)return false;
  const QByteArray sealed=file.readAll();
  QByteArray decoded(sealed.size()-48,0);
  const int count=hbl_resource_open(reinterpret_cast<unsigned char*>(decoded.data()),decoded.size(),reinterpret_cast<const unsigned char*>(sealed.constData()),sealed.size());
  if(count!=decoded.size())return false;
  plain=new QByteArray(decoded);
 }
 if(!QResource::registerResource(reinterpret_cast<const uchar*>(plain->constData()),root))return false;
 roots.append(root);
 QFile status(QStringLiteral("/run/hbl-hotspot-ui/resource.status"));
 if(status.open(QIODevice::WriteOnly))status.write("sealed-resource-registered");
 return true;
}
#endif
