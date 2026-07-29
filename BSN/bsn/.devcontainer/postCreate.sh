cd /workspaces/bsn &&\
    rosdep install --from-paths src --ignore-src -r -y &&\
    catkin_make
    echo "source /workspaces/bsn/devel/setup.sh" >> /root/.bashrc
