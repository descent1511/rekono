<template>
  <b-modal :id="id" @show="fetchUsers" @hidden="clean" @ok="confirm" title="Add Member" ok-title="Add Member" header-bg-variant="dark" header-text-variant="light" ok-variant="dark">
    <b-form ref="add_member_form">
      <b-form-group invalid-feedback="User is required" label="User">
        <b-form-select v-model="member" :options="users" value-field="id" text-field="username" :state="memberState" @change="onUserSelected">
          <template #first>
            <b-form-select-option :value="null">Select a user</b-form-select-option>
          </template>
        </b-form-select>
      </b-form-group>
      <b-form-group label="Role" v-if="showRole">
        <b-form-select v-model="role">
          <b-form-select-option v-if="canAddAdminorOperator" value="admin">Admin</b-form-select-option>
          <b-form-select-option v-if="canAddAdminorOperator" value="operator">Operator</b-form-select-option>
        </b-form-select>
      </b-form-group>
    </b-form>
  </b-modal>
</template>

<script>
import RekonoApi from '@/backend/RekonoApi'
export default {
  name: 'addProjectMemberModal',
  mixins: [RekonoApi],
  props: {
    id: String,
    projectId: [Number, String],
    currentRole: String 
  },
  data () {
    return {
      users: [],
      member: null,
      memberState: null,
      role: null,
      showRole: false,
      canAddAdminorOperator: false,
    }
  },
  methods: {
    fetchUsers () {
      this.getAllPages('/api/users/', { role_project: this.currentRole, project__ne: this.projectId, o: 'username' })
        .then(results => this.users = results)
    },
    check () {
      this.memberState = (this.member !== null)
      return this.memberState
    },
    onUserSelected() {
      if (this.member) {
        const selectedUser = this.users.find(user => user.id === this.member);

        this.canAddAdminorOperator = ['Admin', 'Auditor'].includes(selectedUser.role);

        this.showRole = this.canAddAdminorOperator;

        if (!this.canAddAdminorOperator) {
          this.role = 'member';
        } else {
          this.role = null;
        }
      } else {
        this.showRole = false;
        this.role = null;
      }
    },
    confirm (event) {
      event.preventDefault()
      if (this.check()) {
        this.post(`/api/projects/${this.projectId}/members/`, { user: this.member, role: this.role }, 'New member', 'New member added successfully')
          .then(() => { return Promise.resolve(true) })
          .catch(() => { return Promise.resolve(false) })
          .then(success => { this.$emit('confirm', { id: this.id, success: success, reload: true }) })
      }
    },
    clean () {
      this.member = null
      this.memberState = null
      this.role = null
      this.showRole = false
      this.canAddAdminorOperator = false
    }
  }
}
</script>
