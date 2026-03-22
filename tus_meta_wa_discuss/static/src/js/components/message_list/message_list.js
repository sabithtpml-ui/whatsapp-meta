/** @odoo-module **/

import { MessageList } from '@mail/components/message_list/message_list';
import { patch } from 'web.utils';

patch(MessageList.prototype, 'tus_meta_whatsapp_base/static/src/js/components/message_list/message_list.js', {
        _willPatch() {
        const lastRenderedValues = this._lastRenderedValues();
        if (!lastRenderedValues) {
            return;
        }
        const { messageListView } = lastRenderedValues;
        if (!messageListView.exists()) {
            return;
        }
        this._willPatchSnapshot = {
            scrollHeight: messageListView.getScrollableElement() && messageListView.getScrollableElement().scrollHeight ? messageListView.getScrollableElement().scrollHeight : 0 ,
            scrollTop: messageListView.getScrollableElement() && messageListView.getScrollableElement().scrollHeight ? messageListView.getScrollableElement().scrollTop : 0,
        };
    }
//    get image_url(){
//        if(this.threadView && this.threadView.thread && this.threadView.thread.isWaMsgs &&  this.threadView.thread.model == 'mail.channel' && this.threadView.thread.env && this.threadView.thread.env.session.company_id){
//            return '/web/image/res.company/'+this.threadView.thread.env.session.company_id+'/back_image'
//        }
//        else{
//            return ""
//        }
//    }
});