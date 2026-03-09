import streamlit as st

# 设置页面基本配置
st.set_page_config(
    page_title="物流分析看板总入口",  # 页面标题
    page_icon="📦",  # 页面图标（包裹图标）
    layout="centered",  # 页面布局：居中
    initial_sidebar_state="collapsed"  # 收起侧边栏
)

# 页面标题和说明
st.title("📦 物流分析看板总入口")
st.markdown("---")  # 分隔线
st.write("欢迎使用物流分析看板，点击下方链接进入对应模块：")

# 定义看板数据（名称 + 链接）
dashboard_data = [
    {
        "name": "红单看板",
        "url": "https://logisticsdatapy-kap4prpcmvgg9vm4kfppi4.streamlit.app/",
        "description": "红单物流数据可视化分析"
    },
    {
        "name": "空派看板",
        "url": "https://logisticsdataairpy-q2gmpuhdgbrdavp7ankrdk.streamlit.app/",
        "description": "空派物流数据可视化分析"
    },
    {
        "name": "海运看板",
        "url": "https://logisticsdatashippy-ahvlhdyatc6vzafbqxudts.streamlit.app/",
        "description": "海运物流数据可视化分析",
    },
    {
        "name": "AWD补货看板",
        "url": "https://logisticsdataawdpy-6olhcyqpmqqfu9qwxqrwtj.streamlit.app/",
        "description": "AWD补货物流数据可视化分析"
    }
]

# 循环生成每个看板的链接卡片
for item in dashboard_data:
    # 创建卡片式布局
    with st.container(border=True):
        # 标题 + 链接（蓝色可点击）
        st.subheader(f"[{item['name']}]({item['url']})")
        # 描述信息
        st.caption(item["description"])
        # 添加按钮（可选，额外的点击入口）
        st.link_button(
            label=f"进入{item['name']}",
            url=item["url"],
            use_container_width=True  # 按钮宽度适配容器
        )
    st.write("")  # 空行分隔

# 页脚信息
st.markdown("---")
st.caption("© 物流分析看板 | 如有问题请联系管理员")