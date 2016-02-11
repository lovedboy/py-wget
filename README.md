一个支持断点续传以及多线程下载的小下载器：py-wget

依赖于requests：

 > pip install requests

安装方法：

```
 cd ~
 git clone https://github.com/lovedboy/py-wget.git
 cd py-wget
 chmod u+x py-wget.py
 alias py-wget="`pwd`/py-wget.py"
 py-wget -u "http://nginx.org/download/nginx-1.7.1.tar.gz"
```

Have Fun~
